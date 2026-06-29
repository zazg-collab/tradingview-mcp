"""
CIA (Chronic Investor Academy) Setup Scanner for IDX.

Mendeteksi CIA-specific setups dari seluruh ~866 saham IDX menggunakan
tradingview-screener Query API (bukan coinlist, sehingga mencakup semua saham).

Definisi setup (dari materi CIA TA 2026 + Tradingdiary2):
─────────────────────────────────────────────────────────
SUPERKETAT ⚡
  close > MA5 AND MA10 AND MA20
  AND jarak ke SEMUA MA ≤ tight_pct% (AND condition)
  → Setup entry terbaik, CL ketat di bawah semua MA

KETAT
  close > MA5 AND MA10 AND MA20
  AND jarak ≤ tight_pct% ke SALAH SATU MA (OR condition)
  → Konfirmasi tren mulai; superketat adalah subset dari ketat

KAMEHAMEHA 💥
  volume hari ini > kamehameha_ratio × avg_volume_10d
  → Ledakan volume, sinyal bandar masuk; bisa TANPA setup MA

STAR ⭐
  (ketat ATAU superketat) AND kamehameha di hari yang sama
  → Setup premium terkuat

RAINBOW 🌈
  close > MA5 AND MA10 AND MA20 AND MA50 AND MA100 AND MA200
  → Di atas SEMUA MA, tidak ada resistance; reward tanpa batas

ABOVE_MA20
  close > MA20 (syarat minimal saat IHSG bearish)
  → Safety filter untuk kondisi market sekarang

Catatan teknis:
  - CIA menggunakan SMA (bukan EMA). Screener menggunakan kolom SMA5..SMA200.
  - MA3 tidak tersedia di screener; di-proxy dengan SMA5 (jika di atas MA5
    dan tight, hampir pasti juga di atas MA3 yang lebih pendek).
  - Volume average menggunakan average_volume_60d_calc (V60) — sama dengan CIA original.
    Threshold kamehameha 2.5x V60, persis seperti CIAbot.
    Validated: DYAN vol/V60 = 3.87x (CIAbot report 3.91x ✅)
"""
from __future__ import annotations

from typing import List, Optional

from tradingview_mcp.core.data.idx_indices import IDX_INDICES
from tradingview_mcp.core.data.idx_sectors import get_sector_label

# ── Timeframe mapping ────────────────────────────────────────────────────────
_TF_TO_TV: dict = {
    "1D": "1D", "1W": "1W", "1M": "1M",
    "4H": "240", "4h": "240",
    "1H": "60",  "1h": "60",
    "15m": "15", "5m": "5",
}

# ── Default thresholds ────────────────────────────────────────────────────────
DEFAULT_TIGHT_PCT        = 5.0   # ≤5% jarak ke MA = "ketat"
DEFAULT_KAMEHAMEHA_RATIO = 2.5   # volume > 2.5x V60 — sama persis dengan CIA original
DEFAULT_MIN_VOL_IDR      = 0     # CIAbot tidak filter volume sama sekali (SDRA 134jt masuk)

# ── Setup labels ──────────────────────────────────────────────────────────────
SETUP_SUPERKETAT  = "SUPERKETAT"
SETUP_KETAT       = "KETAT"
SETUP_KAMEHAMEHA  = "KAMEHAMEHA"
SETUP_STAR        = "STAR"
SETUP_RAINBOW     = "RAINBOW"
SETUP_ABOVE_MA20  = "ABOVE_MA20"


def _pct(price: float, ma: Optional[float]) -> Optional[float]:
    """% jarak harga ke MA. Positif = price di atas MA."""
    if not ma or ma <= 0:
        return None
    return round((price - ma) / ma * 100, 2)


def _classify(
    close:     float,
    ma5:       Optional[float],
    ma10:      Optional[float],
    ma20:      Optional[float],
    ma50:      Optional[float],
    ma100:     Optional[float],
    ma200:     Optional[float],
    volume:    float,
    avg_vol:   Optional[float],
    tight_pct: float,
    kame_ratio: float,
) -> tuple[List[str], dict]:
    """
    Klasifikasi setup CIA untuk satu saham.
    Returns: (list_of_setups, ma_distances_dict)
    """
    setups: List[str] = []

    # ── Jarak % ke setiap MA ──────────────────────────────────────────────────
    d5   = _pct(close, ma5)
    d10  = _pct(close, ma10)
    d20  = _pct(close, ma20)
    d50  = _pct(close, ma50)
    d100 = _pct(close, ma100)
    d200 = _pct(close, ma200)

    # ── Boolean: apakah harga di atas MA? ────────────────────────────────────
    above5   = d5   is not None and d5   >= 0
    above10  = d10  is not None and d10  >= 0
    above20  = d20  is not None and d20  >= 0
    above50  = d50  is not None and d50  >= 0
    above100 = d100 is not None and d100 >= 0
    above200 = d200 is not None and d200 >= 0

    # ── Boolean: apakah jarak ke MA ≤ tight_pct? ─────────────────────────────
    tight5   = d5   is not None and 0 <= d5   <= tight_pct
    tight10  = d10  is not None and 0 <= d10  <= tight_pct
    tight20  = d20  is not None and 0 <= d20  <= tight_pct

    # ── SUPERKETAT: di atas MA5/10/20 DAN semua dalam tight_pct (AND) ────────
    if above5 and above10 and above20 and tight5 and tight10 and tight20:
        setups.append(SETUP_SUPERKETAT)

    # ── KETAT: di atas MA5/10/20 DAN salah satu dalam tight_pct (OR) ─────────
    # Superketat adalah subset ketat; jika superketat sudah ada, ketat otomatis
    elif above5 and above10 and above20 and (tight5 or tight10 or tight20):
        setups.append(SETUP_KETAT)

    # ── ABOVE_MA20: syarat minimal (bisa coexist dengan setup lain) ───────────
    if above20:
        setups.append(SETUP_ABOVE_MA20)

    # ── RAINBOW: di atas SEMUA MA ─────────────────────────────────────────────
    if above5 and above10 and above20 and above50 and above100 and above200:
        setups.append(SETUP_RAINBOW)

    # ── KAMEHAMEHA: volume ledakan ────────────────────────────────────────────
    vol_ratio: Optional[float] = None
    if avg_vol and avg_vol > 0 and volume > 0:
        vol_ratio = round(volume / avg_vol, 2)
        if vol_ratio >= kame_ratio:
            setups.append(SETUP_KAMEHAMEHA)

    # ── STAR: ketat/superketat + kamehameha ───────────────────────────────────
    has_ma_setup = SETUP_SUPERKETAT in setups or SETUP_KETAT in setups
    if has_ma_setup and SETUP_KAMEHAMEHA in setups:
        setups.append(SETUP_STAR)

    # ── MA distance summary ───────────────────────────────────────────────────
    ma_dist = {}
    if d5   is not None: ma_dist["ma5_pct"]   = d5
    if d10  is not None: ma_dist["ma10_pct"]  = d10
    if d20  is not None: ma_dist["ma20_pct"]  = d20
    if d50  is not None: ma_dist["ma50_pct"]  = d50
    if d100 is not None: ma_dist["ma100_pct"] = d100
    if d200 is not None: ma_dist["ma200_pct"] = d200
    if vol_ratio is not None: ma_dist["vol_ratio_v60"] = vol_ratio

    return setups, ma_dist


def scan_cia_setups(
    setup_filter:      str   = "all",
    min_volume_idr:    float = DEFAULT_MIN_VOL_IDR,
    index_filter:      str   = "",
    limit:             int   = 50,
    timeframe:         str   = "1D",
    tight_pct:         float = DEFAULT_TIGHT_PCT,
    kamehameha_ratio:  float = DEFAULT_KAMEHAMEHA_RATIO,
    min_above_ma20:    bool  = True,
) -> dict:
    """
    Scan seluruh IDX (~866 saham) untuk CIA-specific setups.

    Args:
        setup_filter:     Filter hasil: "all", "superketat", "ketat", "kamehameha",
                          "star", "rainbow", "above_ma20". Default "all".
        min_volume_idr:   Minimum nilai transaksi harian (IDR). Default 1B IDR.
                          Set 0 untuk no filter.
        index_filter:     Filter ke index: LQ45, IDX30, IDX80, KOMPAS100, dll.
                          Kosong = scan semua IDX.
        limit:            Jumlah hasil per setup (max 100). Default 50.
        timeframe:        Timeframe: 1D (default), 1W, 1H, 4H, 15m.
        tight_pct:        Threshold % jarak ke MA untuk "ketat". Default 5.0%.
        kamehameha_ratio: Threshold volume vs avg10d untuk kamehameha. Default 2.0x.
        min_above_ma20:   Jika True, hanya tampilkan saham di atas MA20 (kondisi
                          IHSG bearish saat ini). Default True.

    Returns:
        dict berisi:
          - setups: {setup_name: [list saham]}
          - summary: count per setup
          - scan_info: parameter yang dipakai
          - total_scanned, total_with_setup
    """
    try:
        from tradingview_screener import Query
    except ImportError:
        return {"error": "tradingview-screener tidak tersedia. Jalankan: uv sync"}

    # ── Normalize inputs ──────────────────────────────────────────────────────
    suffix      = _TF_TO_TV.get(timeframe, "1D")
    setup_filter = setup_filter.lower().replace("-", "_")
    limit       = max(1, min(100, limit))

    def _c(name: str) -> str:
        """Tambah suffix timeframe ke nama kolom jika bukan 1D."""
        return f"{name}|{suffix}" if suffix != "1D" else name

    # ── Columns to fetch ──────────────────────────────────────────────────────
    cols = [
        _c("open"), _c("close"), _c("volume"), _c("change"),
        _c("SMA5"), _c("SMA10"), _c("SMA20"),
        _c("SMA50"), _c("SMA100"), _c("SMA200"),
        "average_volume_60d_calc",
        "RSI", "name", "sector",
    ]

    # ── Build query ───────────────────────────────────────────────────────────
    q = (Query()
         .set_markets("indonesia")
         .select(*cols)
         .order_by(_c("volume"), ascending=False)
         .limit(1000))

    if index_filter:
        idx_key = index_filter.strip().upper()
        if idx_key in IDX_INDICES:
            raw_syms = IDX_INDICES[idx_key]["get_symbols"]()
            tv_syms  = [s if s.startswith("IDX:") else f"IDX:{s}" for s in raw_syms]
            q = q.set_tickers(*tv_syms)
        else:
            return {
                "error"    : f"Index tidak dikenal: {index_filter}",
                "available": list(IDX_INDICES.keys()),
            }

    # ── Fetch data ────────────────────────────────────────────────────────────
    try:
        total, df = q.get_scanner_data()
    except Exception as exc:
        return {"error": f"Gagal fetch data: {exc}"}

    if df is None or df.empty:
        return {"error": "Tidak ada data dari IDX"}

    # Normalize kolom: hapus suffix (mis "SMA20|240" → "SMA20")
    df.rename(columns=lambda c: c.split("|")[0] if isinstance(c, str) else c, inplace=True)

    # ── Classify each stock ───────────────────────────────────────────────────
    buckets: dict[str, List[dict]] = {
        SETUP_STAR       : [],
        SETUP_SUPERKETAT : [],
        SETUP_KETAT      : [],
        SETUP_KAMEHAMEHA : [],
        SETUP_RAINBOW    : [],
        SETUP_ABOVE_MA20 : [],
    }

    total_with_setup = 0

    for _, row in df.iterrows():
        sym    = str(row.get("ticker", ""))
        close  = row.get("close")  or 0
        volume = row.get("volume") or 0
        change = row.get("change") or 0

        if not close or close <= 0:
            continue

        # Filter likuiditas
        vol_idr = volume * close
        if min_volume_idr > 0 and vol_idr < min_volume_idr:
            continue

        # Ambil nilai MA
        ma5   = row.get("SMA5")
        ma10  = row.get("SMA10")
        ma20  = row.get("SMA20")
        ma50  = row.get("SMA50")
        ma100 = row.get("SMA100")
        ma200 = row.get("SMA200")
        avg_vol = row.get("average_volume_60d_calc")

        # Filter above MA20 jika diminta
        if min_above_ma20 and ma20 and close <= ma20:
            continue

        setups, ma_dist = _classify(
            close=close, ma5=ma5, ma10=ma10, ma20=ma20,
            ma50=ma50, ma100=ma100, ma200=ma200,
            volume=volume, avg_vol=avg_vol,
            tight_pct=tight_pct, kame_ratio=kamehameha_ratio,
        )

        if not setups:
            continue

        ticker = sym.replace("IDX:", "")
        rsi    = row.get("RSI")
        sector = str(row.get("sector") or get_sector_label(ticker))

        entry: dict = {
            "ticker"    : ticker,
            "name"      : str(row.get("name", "")),
            "price"     : round(close),
            "change_pct": round(change, 2),
            "volume_idr": round(vol_idr / 1_000_000, 1),
            "rsi"       : round(rsi, 1) if rsi else None,
            "setups"    : setups,
            "sector"    : sector,
            **ma_dist,
        }

        # Masukkan ke bucket yang relevan
        placed = False
        for s in [SETUP_STAR, SETUP_SUPERKETAT, SETUP_KETAT,
                  SETUP_KAMEHAMEHA, SETUP_RAINBOW, SETUP_ABOVE_MA20]:
            if s in setups:
                buckets[s].append(entry)
                placed = True

        if placed:
            total_with_setup += 1

    # ── Filter by setup_filter ────────────────────────────────────────────────
    _filter_map = {
        "all"        : list(buckets.keys()),
        "superketat" : [SETUP_SUPERKETAT],
        "ketat"      : [SETUP_KETAT, SETUP_SUPERKETAT],  # superketat is ketat
        "kamehameha" : [SETUP_KAMEHAMEHA],
        "star"       : [SETUP_STAR],
        "rainbow"    : [SETUP_RAINBOW],
        "above_ma20" : [SETUP_ABOVE_MA20],
    }
    active_setups = _filter_map.get(setup_filter, list(buckets.keys()))

    # Sort each bucket: STAR/superketat by tightest MA, kamehameha by vol_ratio
    def _sort_key(entry: dict, stype: str) -> float:
        if stype in (SETUP_KAMEHAMEHA,):
            return -(entry.get("vol_ratio_vs_avg10d") or 0)
        # For MA setups: sort by minimum MA distance (tightest = best entry)
        dists = [
            v for k, v in entry.items()
            if k.endswith("_pct") and isinstance(v, (int, float)) and v >= 0
        ]
        return min(dists) if dists else 999

    result_setups: dict = {}
    for sname in active_setups:
        bucket = buckets.get(sname, [])
        bucket_sorted = sorted(bucket, key=lambda e: _sort_key(e, sname))
        result_setups[sname] = bucket_sorted[:limit]

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = {s: len(buckets[s]) for s in buckets}

    return {
        "scan_info": {
            "timeframe"        : timeframe,
            "index_filter"     : index_filter or "All IDX",
            "tight_pct"        : tight_pct,
            "kamehameha_ratio" : kamehameha_ratio,
            "min_volume_idr_M" : round(min_volume_idr / 1_000_000, 0),
            "min_above_ma20"   : min_above_ma20,
            "setup_filter"     : setup_filter,
        },
        "total_scanned"   : total,
        "total_with_setup": total_with_setup,
        "summary"         : summary,
        "setups"          : result_setups,
    }


def scan_sector_rotation(
    timeframe:  str   = "1D",
    tight_pct:  float = DEFAULT_TIGHT_PCT,
    min_volume_idr: float = 0,
) -> dict:
    """
    Scan sektor IDX: berapa % saham di atas MA20/50/200 dan berapa yg ketat/superketat.
    Digunakan untuk tahu sektor mana yang sedang 'jalan' vs lemah.

    Returns list sektor diurutkan dari terkuat (paling banyak above MA20) ke terlemah.
    """
    try:
        from tradingview_screener import Query
    except ImportError:
        return {"error": "tradingview-screener tidak tersedia"}

    suffix = _TF_TO_TV.get(timeframe, "1D")

    def _c(name: str) -> str:
        return f"{name}|{suffix}" if suffix != "1D" else name

    cols = [
        _c("close"), _c("volume"), _c("change"),
        _c("SMA5"), _c("SMA10"), _c("SMA20"), _c("SMA50"), _c("SMA200"),
        "sector", "name",
    ]

    try:
        total, df = (Query()
                     .set_markets("indonesia")
                     .select(*cols)
                     .limit(1000)
                     .get_scanner_data())
    except Exception as exc:
        return {"error": f"Gagal fetch: {exc}"}

    df.rename(columns=lambda c: c.split("|")[0] if isinstance(c, str) else c, inplace=True)

    # Accumulate per sektor
    from collections import defaultdict
    sectors: dict = defaultdict(lambda: {
        "total": 0, "above_ma20": 0, "above_ma50": 0, "above_ma200": 0,
        "ketat": 0, "superketat": 0, "rainbow": 0,
        "vol_idr_total": 0.0,
    })

    for _, row in df.iterrows():
        close  = row.get("close") or 0
        volume = row.get("volume") or 0
        if not close or close <= 0:
            continue

        vol_idr = volume * close
        if min_volume_idr > 0 and vol_idr < min_volume_idr:
            continue

        sector = str(row.get("sector") or "Lainnya").strip() or "Lainnya"
        ma5    = row.get("SMA5")
        ma10   = row.get("SMA10")
        ma20   = row.get("SMA20")
        ma50   = row.get("SMA50")
        ma200  = row.get("SMA200")

        s = sectors[sector]
        s["total"] += 1
        s["vol_idr_total"] += vol_idr / 1_000_000  # dalam juta IDR

        above20  = ma20  and close > ma20
        above50  = ma50  and close > ma50
        above200 = ma200 and close > ma200

        if above20:  s["above_ma20"]  += 1
        if above50:  s["above_ma50"]  += 1
        if above200: s["above_ma200"] += 1

        # Ketat/Superketat
        if ma5 and ma10 and ma20 and close > ma5 and close > ma10 and close > ma20:
            d5  = (close - ma5)  / ma5  * 100
            d10 = (close - ma10) / ma10 * 100
            d20 = (close - ma20) / ma20 * 100
            tight5  = 0 <= d5  <= tight_pct
            tight10 = 0 <= d10 <= tight_pct
            tight20 = 0 <= d20 <= tight_pct
            if tight5 and tight10 and tight20:
                s["superketat"] += 1
                s["ketat"] += 1
            elif tight5 or tight10 or tight20:
                s["ketat"] += 1

        # Rainbow
        if (ma5 and ma10 and ma20 and ma50 and ma200 and
                close > ma5 and close > ma10 and close > ma20 and
                close > ma50 and close > ma200):
            s["rainbow"] += 1

    # Build output — sort by % above MA20 descending
    result = []
    for sector_name, s in sectors.items():
        n = s["total"]
        if n == 0:
            continue
        pct20  = round(s["above_ma20"]  / n * 100, 1)
        pct50  = round(s["above_ma50"]  / n * 100, 1)
        pct200 = round(s["above_ma200"] / n * 100, 1)

        # Health score: weighted average
        health = round(pct20 * 0.5 + pct50 * 0.3 + pct200 * 0.2, 1)

        # Strength label
        if health >= 60:
            strength = "🔥 KUAT"
        elif health >= 40:
            strength = "📈 MODERAT"
        elif health >= 20:
            strength = "📉 LEMAH"
        else:
            strength = "❄️ SANGAT LEMAH"

        result.append({
            "sector"         : sector_name,
            "strength"       : strength,
            "health_score"   : health,
            "total_stocks"   : n,
            "above_ma20"     : s["above_ma20"],
            "above_ma50"     : s["above_ma50"],
            "above_ma200"    : s["above_ma200"],
            "pct_above_ma20" : pct20,
            "pct_above_ma50" : pct50,
            "pct_above_ma200": pct200,
            "ketat_count"    : s["ketat"],
            "superketat_count": s["superketat"],
            "rainbow_count"  : s["rainbow"],
            "vol_idr_total_B": round(s["vol_idr_total"] / 1000, 2),  # miliar
        })

    result.sort(key=lambda x: x["health_score"], reverse=True)

    return {
        "scan_info": {
            "timeframe"     : timeframe,
            "tight_pct"     : tight_pct,
            "total_sectors" : len(result),
            "total_stocks"  : sum(s["total_stocks"] for s in result),
        },
        "sectors": result,
    }
