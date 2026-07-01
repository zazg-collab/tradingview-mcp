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

import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from tradingview_mcp.core.data.idx_indices import IDX_INDICES
from tradingview_mcp.core.data.idx_sectors import get_sector_label

# ── Telegram knowledge base ───────────────────────────────────────────────────
_TG_DB_PATH = os.path.expanduser("~/.mcp_atila_knowledge.db")


def _tg_signal_for_ticker(ticker: str) -> dict:
    """
    Query the Telegram knowledge base SQLite DB for community signals about
    a given ticker. Returns a dict with mentions count, last mention date,
    whether CIAbot IHSG Alert group mentioned it, and sentiment.

    Returns {"available": False} if the DB is missing or any error occurs.
    """
    try:
        if not os.path.exists(_TG_DB_PATH):
            return {"available": False}

        conn = sqlite3.connect(_TG_DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        pattern = f"%{ticker}%"

        # Count mentions in last 7 days + get last mention date + check CIAbot group
        cursor.execute(
            """
            SELECT
                COUNT(*) AS mentions_7d,
                MAX(date) AS last_mention,
                SUM(CASE WHEN group_name LIKE '%CIAbot IHSG Alert%' THEN 1 ELSE 0 END) AS ciabot_count
            FROM messages
            WHERE tickers LIKE ?
              AND date >= ?
            """,
            (pattern, cutoff),
        )
        row = cursor.fetchone()

        mentions_7d  = int(row["mentions_7d"] or 0)
        last_mention = row["last_mention"]
        ciabot_alert = int(row["ciabot_count"] or 0) > 0

        # Sentiment: pick the most recent non-null sentiment in the window
        sentiment = "NEUTRAL"
        if mentions_7d > 0:
            cursor.execute(
                """
                SELECT sentiment FROM messages
                WHERE tickers LIKE ?
                  AND date >= ?
                  AND sentiment IS NOT NULL
                  AND sentiment != ''
                ORDER BY date DESC
                LIMIT 1
                """,
                (pattern, cutoff),
            )
            sent_row = cursor.fetchone()
            if sent_row and sent_row["sentiment"]:
                sentiment = str(sent_row["sentiment"]).upper()

        conn.close()

        # Trim last_mention to "YYYY-MM-DD HH:MM" for readability
        if last_mention and len(last_mention) > 16:
            last_mention = last_mention[:16]

        return {
            "available"   : True,
            "mentions_7d" : mentions_7d,
            "last_mention": last_mention,
            "ciabot_alert": ciabot_alert,
            "sentiment"   : sentiment,
        }

    except Exception:
        return {"available": False}


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

# ── Entry timing / risk thresholds ───────────────────────────────────────────
MIN_DAILY_LOT_VOLUME   = 10_000  # Minimum avg V60 (lot) — filter XCID (700), STTP (2800)
ALREADY_RAN_PCT        = 5.0     # change% hari ini → HIGH_RISK_ALREADY_RAN (butuh +20% lagi)
EXTENDED_MA20_PCT      = 12.0    # % di atas MA20 → EXTENDED (terlalu jauh, risiko pullback)
RUNNING_PCT            = 2.0     # change% → RUNNING (sedang jalan, entry kurang ideal)

# ── Setup labels ──────────────────────────────────────────────────────────────
SETUP_SUPERKETAT  = "SUPERKETAT"
SETUP_KETAT       = "KETAT"
SETUP_KAMEHAMEHA  = "KAMEHAMEHA"
SETUP_STAR        = "STAR"
SETUP_RAINBOW     = "RAINBOW"
SETUP_ABOVE_MA20  = "ABOVE_MA20"
SETUP_BELOWALLMA  = "BELOWALLMA"
SETUP_SUNFLOWER   = "SUNFLOWER"
SETUP_EMPTY_ZONE  = "EMPTY_ZONE"


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

    # ── BELOWALLMA: di bawah SEMUA MA (kebalikan RAINBOW) ────────────────────
    below5   = d5   is not None and d5   < 0
    below10  = d10  is not None and d10  < 0
    below20  = d20  is not None and d20  < 0
    below50  = d50  is not None and d50  < 0
    below100 = d100 is not None and d100 < 0
    below200 = d200 is not None and d200 < 0
    if below5 and below10 and below20 and below50 and below100 and below200:
        setups.append(SETUP_BELOWALLMA)

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


def _get_entry_timing(
    change_pct: float,
    ma20_pct:   Optional[float],
    avg_vol:    Optional[float],
) -> str:
    """
    Tentukan timing entry setup hari ini:

    ILLIQUID           — avg V60 < MIN_DAILY_LOT_VOLUME (susah keluar, skip)
    EXTENDED           — jarak ke MA20 > EXTENDED_MA20_PCT (terlalu jauh, risiko pullback)
    HIGH_RISK_ALREADY_RAN — naik >ALREADY_RAN_PCT% hari ini (butuh +20% lagi esok untuk ARA)
    RUNNING            — naik RUNNING_PCT..ALREADY_RAN_PCT% (sedang jalan, entry kurang ideal)
    FRESH              — belum naik, setup baru siap entry sore/besok ✅
    """
    if avg_vol is not None and avg_vol < MIN_DAILY_LOT_VOLUME:
        return "ILLIQUID"
    if ma20_pct is not None and ma20_pct > EXTENDED_MA20_PCT:
        return "EXTENDED"
    if change_pct >= ALREADY_RAN_PCT:
        return "HIGH_RISK_ALREADY_RAN"
    if change_pct >= RUNNING_PCT:
        return "RUNNING"
    return "FRESH"


_ENTRY_TIMING_RANK: dict = {
    "FRESH"                : 0,
    "RUNNING"              : 1,
    "HIGH_RISK_ALREADY_RAN": 2,
    "EXTENDED"             : 3,
    "ILLIQUID"             : 9,   # seharusnya sudah di-filter sebelum masuk results
}


def _check_historical_setups(
    ticker:    str,
    tight_pct: float,
    ara_pct:   float = 10.0,   # threshold % naik untuk dianggap "big move/ARA"
    lookback:  int   = 20,     # hari histori untuk SMA & pattern check
) -> List[str]:
    """
    Cek SUNFLOWER dan EMPTY_ZONE menggunakan history OHLCV (via yfinance).
    Hanya dipanggil untuk saham yang sudah di-identify sebagai ketat/superketat.

    SUNFLOWER 🌻 = ketat hari ini, tapi hari sebelumnya TIDAK ketat
                   (first ketat signal setelah jeda)

    EMPTY_ZONE ⬛ = volume flat hari ini (<50% V20-avg), tapi 3 hari sebelumnya
                   ada bar naik >ara_pct% (ARA atau big move)
                   → distribusi terselubung, jebakan retailer
    """
    try:
        import yfinance as yf
        import pandas as pd

        hist = yf.download(
            f"{ticker}.JK",
            period=f"{lookback + 5}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if hist is None or len(hist) < 6:
            return []

        hist = hist.tail(lookback)
        c = hist["Close"].squeeze()
        v = hist["Volume"].squeeze()

        # Rolling SMAs dari data historis
        sma5  = c.rolling(5,  min_periods=3).mean()
        sma10 = c.rolling(10, min_periods=5).mean()
        sma20 = c.rolling(20, min_periods=10).mean()

        def _is_ketat_row(i: int) -> bool:
            """Cek apakah bar ke-i ketat."""
            try:
                close_i = float(c.iloc[i])
                m5  = float(sma5.iloc[i])
                m10 = float(sma10.iloc[i])
                m20 = float(sma20.iloc[i])
            except Exception:
                return False
            if any(v != v for v in [close_i, m5, m10, m20]):  # NaN check
                return False
            if not (close_i > m5 and close_i > m10 and close_i > m20):
                return False
            d5  = (close_i - m5)  / m5  * 100
            d10 = (close_i - m10) / m10 * 100
            d20 = (close_i - m20) / m20 * 100
            return d5 <= tight_pct or d10 <= tight_pct or d20 <= tight_pct

        n = len(hist)
        found: List[str] = []

        # ── SUNFLOWER ─────────────────────────────────────────────────────────
        today_ketat    = _is_ketat_row(n - 1)
        yest_ketat     = _is_ketat_row(n - 2) if n >= 2 else False

        if today_ketat and not yest_ketat:
            # Hitung berapa hari berturut-turut TIDAK ketat sebelum hari ini
            days_gap = 0
            for j in range(n - 2, -1, -1):
                if _is_ketat_row(j):
                    break
                days_gap += 1
            if days_gap >= 1:
                found.append(f"SUNFLOWER (ketat pertama setelah {days_gap}h gap)")

        # ── EMPTY ZONE ────────────────────────────────────────────────────────
        # Ada big move (>ara_pct) dalam 3 bar sebelumnya?
        big_move_days_ago = None
        for j in range(1, min(4, n)):           # cek 3 bar ke belakang
            try:
                prev_c = float(c.iloc[n - j - 1])
                curr_c = float(c.iloc[n - j])
                if prev_c > 0 and (curr_c - prev_c) / prev_c * 100 >= ara_pct:
                    big_move_days_ago = j
                    break
            except Exception:
                pass

        if big_move_days_ago is not None:
            # Volume hari ini vs avg20
            v20_avg = float(v.tail(20).mean())
            v_today = float(v.iloc[-1])
            if v20_avg > 0 and v_today < v20_avg * 0.5:
                found.append(
                    f"EMPTY_ZONE (vol={round(v_today/v20_avg*100)}% avg, "
                    f"big move {big_move_days_ago}h lalu)"
                )

        return found

    except Exception:
        return []


def scan_cia_setups(
    setup_filter:       str   = "all",
    min_volume_idr:     float = DEFAULT_MIN_VOL_IDR,
    index_filter:       str   = "",
    limit:              int   = 50,
    timeframe:          str   = "1D",
    tight_pct:          float = DEFAULT_TIGHT_PCT,
    kamehameha_ratio:   float = DEFAULT_KAMEHAMEHA_RATIO,
    min_above_ma20:     bool  = True,
    min_avg_lot_volume: int   = MIN_DAILY_LOT_VOLUME,
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
        SETUP_BELOWALLMA : [],
        SETUP_SUNFLOWER  : [],
        SETUP_EMPTY_ZONE : [],
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

        # Filter minimum likuiditas (V60) — skip saham susah keluar (XCID vol 700, STTP vol 2800)
        if min_avg_lot_volume > 0 and (avg_vol is None or avg_vol < min_avg_lot_volume):
            continue

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

        _change = round(change, 2)
        entry: dict = {
            "ticker"          : ticker,
            "name"            : str(row.get("name", "")),
            "price"           : round(close),
            "change_pct"      : _change,
            "volume_idr"      : round(vol_idr / 1_000_000, 1),
            "rsi"             : round(rsi, 1) if rsi else None,
            "setups"          : setups,
            "sector"          : sector,
            "entry_timing"    : _get_entry_timing(
                change_pct=_change,
                ma20_pct=ma_dist.get("ma20_pct"),
                avg_vol=avg_vol,
            ),
            "telegram_signal" : _tg_signal_for_ticker(ticker),
            **ma_dist,
        }

        # Masukkan ke bucket yang relevan
        placed = False
        for s in [SETUP_STAR, SETUP_SUPERKETAT, SETUP_KETAT,
                  SETUP_KAMEHAMEHA, SETUP_RAINBOW, SETUP_ABOVE_MA20,
                  SETUP_BELOWALLMA]:
            if s in setups:
                buckets[s].append(entry)
                placed = True

        if placed:
            total_with_setup += 1

    # ── Post-process: SUNFLOWER + EMPTY_ZONE via historical check ────────────
    # Hanya untuk kandidat ketat/superketat (bukan semua 866 saham)
    _hist_candidates = buckets[SETUP_SUPERKETAT] + buckets[SETUP_KETAT]
    for entry in _hist_candidates:
        _ticker = entry["ticker"]
        hist_setups = _check_historical_setups(_ticker, tight_pct=tight_pct)
        if hist_setups:
            entry["setups"] = entry["setups"] + hist_setups
            for hs in hist_setups:
                if hs.startswith("SUNFLOWER"):
                    buckets[SETUP_SUNFLOWER].append(entry)
                elif hs.startswith("EMPTY_ZONE"):
                    buckets[SETUP_EMPTY_ZONE].append(entry)

    # ── Filter by setup_filter ────────────────────────────────────────────────
    _filter_map = {
        "all"        : list(buckets.keys()),
        "superketat" : [SETUP_SUPERKETAT],
        "ketat"      : [SETUP_KETAT, SETUP_SUPERKETAT],  # superketat is ketat
        "kamehameha" : [SETUP_KAMEHAMEHA],
        "star"       : [SETUP_STAR],
        "rainbow"    : [SETUP_RAINBOW],
        "above_ma20" : [SETUP_ABOVE_MA20],
        "belowallma" : [SETUP_BELOWALLMA],
        "sunflower"  : [SETUP_SUNFLOWER],
        "empty_zone" : [SETUP_EMPTY_ZONE],
    }
    active_setups = _filter_map.get(setup_filter, list(buckets.keys()))

    # Sort each bucket: primary = entry_timing rank (FRESH first), secondary = tightness/vol
    def _sort_key(entry: dict, stype: str) -> tuple:
        timing_rank = _ENTRY_TIMING_RANK.get(entry.get("entry_timing", "FRESH"), 0)
        if stype in (SETUP_KAMEHAMEHA,):
            secondary: float = -(entry.get("vol_ratio_v60") or 0)
        else:
            # For MA setups: sort by minimum MA distance (tightest = best entry)
            dists = [
                v for k, v in entry.items()
                if k.endswith("_pct") and isinstance(v, (int, float)) and v >= 0
            ]
            secondary = min(dists) if dists else 999.0
        return (timing_rank, secondary)

    result_setups: dict = {}
    for sname in active_setups:
        bucket = buckets.get(sname, [])
        bucket_sorted = sorted(bucket, key=lambda e: _sort_key(e, sname))
        result_setups[sname] = bucket_sorted[:limit]

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = {s: len(buckets[s]) for s in buckets}

    return {
        "scan_info": {
            "timeframe"           : timeframe,
            "index_filter"        : index_filter or "All IDX",
            "tight_pct"           : tight_pct,
            "kamehameha_ratio"    : kamehameha_ratio,
            "min_volume_idr_M"    : round(min_volume_idr / 1_000_000, 0),
            "min_avg_lot_volume"  : min_avg_lot_volume,
            "min_above_ma20"      : min_above_ma20,
            "setup_filter"        : setup_filter,
        },
        "total_scanned"   : total,
        "total_with_setup": total_with_setup,
        "summary"         : summary,
        "setups"          : result_setups,
    }


def scan_cia_tg_confirmed(
    setup_filter:    str = "star",
    days_back:       int = 7,
    min_tg_mentions: int = 1,
    index_filter:    str = "",
    limit:           int = 20,
) -> dict:
    """
    Double-confirmation scanner: CIA technical setups + Telegram CIAbot alerts.

    Combines scan_cia_setups (technical) with the Telegram knowledge base
    (community signal) to surface stocks that have BOTH a strong CIA technical
    setup AND at least one recent mention/alert in Telegram — especially from
    the CIAbot IHSG Alert group.

    Args:
        setup_filter:    Which CIA setups to include: "star", "kame" (kamehameha),
                         "all_premium" (star + kame combined). Default "star".
        days_back:       How many days back to search the Telegram DB. Default 7.
        min_tg_mentions: Minimum total Telegram mentions to count as "confirmed".
                         Default 1.
        index_filter:    Filter to a specific index: LQ45, IDX30, IDX80, etc.
                         Empty = all IDX.
        limit:           Max results to return (sorted by confirmation_score). Default 20.

    Returns:
        dict with scan_type, setup_filter, days_back, total_scanned,
        double_confirmed_count, and results list.

    Result per stock:
        ticker, price, change_pct, setups, vol_ratio_v60,
        tg_mentions, ciabot_alerts, double_confirmed, confirmation_score

    Scoring:
        cia_setup_score: STAR=10, KAME+RAINBOW=8, SUPERKETAT=6, KETAT=4
        confirmation_score = cia_setup_score + (tg_mentions * 2) + (ciabot_alerts * 5)
    """
    # ── Step 1: Map setup_filter to scan_cia_setups parameter ─────────────────
    _filter_map = {
        "star"       : "star",
        "kame"       : "kamehameha",
        "all_premium": "all",   # will be filtered to star+kame below
    }
    tv_setup = _filter_map.get(setup_filter.lower(), "star")

    cia_result = scan_cia_setups(
        setup_filter    = tv_setup,
        min_volume_idr  = 0,
        index_filter    = index_filter,
        limit           = 500,
        timeframe       = "1D",
        tight_pct       = DEFAULT_TIGHT_PCT,
        kamehameha_ratio= DEFAULT_KAMEHAMEHA_RATIO,
        min_above_ma20  = True,
    )

    if "error" in cia_result:
        return cia_result

    # ── Step 2: Flatten relevant buckets into a single candidate list ──────────
    setups_dict = cia_result.get("setups", {})

    if setup_filter.lower() == "star":
        bucket_keys = [SETUP_STAR]
    elif setup_filter.lower() == "kame":
        bucket_keys = [SETUP_KAMEHAMEHA]
    elif setup_filter.lower() == "all_premium":
        bucket_keys = [SETUP_STAR, SETUP_KAMEHAMEHA]
    else:
        bucket_keys = [SETUP_STAR]

    # Deduplicate by ticker (a stock can appear in multiple buckets)
    seen_tickers: set = set()
    candidates: list = []
    for bkey in bucket_keys:
        for entry in setups_dict.get(bkey, []):
            t = entry.get("ticker", "")
            if t and t not in seen_tickers:
                seen_tickers.add(t)
                candidates.append(entry)

    total_scanned = len(candidates)

    if not candidates or not os.path.exists(_TG_DB_PATH):
        # Return CIA-only results with zeroed TG fields
        results = []
        for entry in candidates[:limit]:
            setups = entry.get("setups", [])
            cia_score = _cia_setup_score(setups)
            r = {
                "ticker"            : entry["ticker"],
                "price"             : entry.get("price"),
                "change_pct"        : entry.get("change_pct"),
                "setups"            : setups,
                "vol_ratio_v60"     : entry.get("vol_ratio_v60"),
                "entry_timing"      : entry.get("entry_timing", "FRESH"),
                "tg_mentions"       : 0,
                "ciabot_alerts"     : 0,
                "double_confirmed"  : False,
                "confirmation_score": cia_score,
            }
            results.append(r)
        return {
            "scan_type"            : "cia_tg_confirmed",
            "setup_filter"         : setup_filter,
            "days_back"            : days_back,
            "total_scanned"        : total_scanned,
            "double_confirmed_count": 0,
            "note"                 : "Telegram DB not available — CIA-only results",
            "results"              : results,
        }

    # ── Step 3: Batch-query Telegram DB for all candidate tickers ─────────────
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    tg_data: dict = {}   # ticker → {"tg_mentions": int, "ciabot_alerts": int}

    try:
        conn = sqlite3.connect(_TG_DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for ticker in seen_tickers:
            pattern = f"%{ticker}%"
            try:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_mentions,
                        SUM(CASE WHEN group_name LIKE '%CIAbot IHSG Alert%' THEN 1 ELSE 0 END)
                            AS ciabot_count
                    FROM messages
                    WHERE tickers LIKE ?
                      AND date >= ?
                    """,
                    (pattern, cutoff),
                )
                row = cursor.fetchone()
                tg_data[ticker] = {
                    "tg_mentions"  : int(row["total_mentions"] or 0),
                    "ciabot_alerts": int(row["ciabot_count"]   or 0),
                }
            except Exception:
                tg_data[ticker] = {"tg_mentions": 0, "ciabot_alerts": 0}

        conn.close()
    except Exception:
        # DB open failed — proceed with zeroes
        for ticker in seen_tickers:
            tg_data[ticker] = {"tg_mentions": 0, "ciabot_alerts": 0}

    # ── Step 4: Build enriched result list ────────────────────────────────────
    results = []
    for entry in candidates:
        ticker = entry.get("ticker", "")
        setups = entry.get("setups", [])
        tg     = tg_data.get(ticker, {"tg_mentions": 0, "ciabot_alerts": 0})

        tg_mentions   = tg["tg_mentions"]
        ciabot_alerts = tg["ciabot_alerts"]

        cia_score = _cia_setup_score(setups)
        conf_score = cia_score + (tg_mentions * 2) + (ciabot_alerts * 5)

        double_confirmed = (tg_mentions >= min_tg_mentions) and (ciabot_alerts > 0)

        results.append({
            "ticker"            : ticker,
            "price"             : entry.get("price"),
            "change_pct"        : entry.get("change_pct"),
            "setups"            : setups,
            "vol_ratio_v60"     : entry.get("vol_ratio_v60"),
            "entry_timing"      : entry.get("entry_timing", "FRESH"),
            "tg_mentions"       : tg_mentions,
            "ciabot_alerts"     : ciabot_alerts,
            "double_confirmed"  : double_confirmed,
            "confirmation_score": conf_score,
        })

    # ── Step 5: Sort by entry_timing rank first (FRESH first), then confirmation_score desc
    results.sort(key=lambda x: (
        _ENTRY_TIMING_RANK.get(x.get("entry_timing", "FRESH"), 0),
        -x["confirmation_score"],
    ))
    results = results[:limit]

    double_confirmed_count = sum(1 for r in results if r["double_confirmed"])

    return {
        "scan_type"             : "cia_tg_confirmed",
        "setup_filter"          : setup_filter,
        "days_back"             : days_back,
        "min_tg_mentions"       : min_tg_mentions,
        "index_filter"          : index_filter or "All IDX",
        "total_scanned"         : total_scanned,
        "double_confirmed_count": double_confirmed_count,
        "results"               : results,
    }


def _cia_setup_score(setups: list) -> int:
    """
    Return a numeric score for the strongest CIA setup in the list.
    STAR=10, KAME+RAINBOW=8, SUPERKETAT=6, KETAT=4, anything else=2.
    """
    if SETUP_STAR in setups:
        return 10
    has_kame    = SETUP_KAMEHAMEHA in setups
    has_rainbow = SETUP_RAINBOW    in setups
    if has_kame and has_rainbow:
        return 8
    if SETUP_SUPERKETAT in setups:
        return 6
    if SETUP_KETAT in setups:
        return 4
    return 2


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
