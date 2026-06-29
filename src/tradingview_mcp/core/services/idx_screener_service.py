"""
IDX Stock Screener & Index Analysis.

Port dari egx_service.py untuk Bursa Efek Indonesia:
  - screen_idx_stocks()   : batch scan IDX universe, rank by score, return top picks
  - analyze_idx_index()   : scan konstituen sebuah index, tampilkan breadth + sektor

Perbedaan utama vs EGX:
  - screener = "indonesia"
  - Semua saham IDR → currency="IDR" tapi pakai compute_stock_score dengan
    currency="USD" (threshold lebih rendah) + IDR liquidity override terpisah
  - Liquidity thresholds: 100M / 500M / 2B IDR/hari (vs EGP 100K/500K/1M)
  - Pct_rank dihitung inline dari batch yang sama (lebih efisien)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ── tradingview_ta via screener_provider ──────────────────────────────────────
try:
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as _get_multiple_analysis,
        fetch_atr_for_tickers,
        fetch_atr_for_ticker,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

from tradingview_mcp.core.services.indicators import (
    compute_stock_score,
    compute_trade_setup,
    compute_trade_quality,
    compute_metrics,
    extract_extended_indicators,
)
from tradingview_mcp.core.data.idx_sectors import get_sector, get_sector_label
from tradingview_mcp.core.data.idx_indices import IDX_INDICES
from tradingview_mcp.core.services.coinlist import load_symbols

_IDX_SCREENER = "indonesia"

# ── IDR Liquidity thresholds ──────────────────────────────────────────────────
_IDR_VAL_FLOOR  = 100_000_000    # 100 juta IDR/hari → minimum viable
_IDR_VAL_LOW    = 500_000_000    # 500 juta IDR/hari → low liquidity
_IDR_VAL_MODEST = 2_000_000_000  # 2 miliar IDR/hari → decent liquidity


def _idr_liquidity_check(avg_vol: Optional[float], close: Optional[float]) -> dict:
    """
    Evaluasi likuiditas berdasarkan nilai IDR/hari.
    Mirip dengan _idr_liquidity_check di idx_decision_service.py.
    """
    if not avg_vol or not close or avg_vol <= 0 or close <= 0:
        return {"grade_cap": None, "penalty": 0, "status": "Unknown", "warnings": []}

    avg_value_idr = avg_vol * close
    warnings: List[str] = []
    penalty  = 0
    grade_cap = None

    if avg_value_idr < _IDR_VAL_FLOOR:
        warnings.append(f"Likuiditas sangat rendah ({avg_value_idr/1e6:.0f}M IDR/hari < 100M)")
        penalty   = 20
        grade_cap = "D"
        status    = "Fail — Sangat Rendah"
    elif avg_value_idr < _IDR_VAL_LOW:
        warnings.append(f"Likuiditas rendah ({avg_value_idr/1e6:.0f}M IDR/hari < 500M)")
        penalty   = 10
        grade_cap = "C"
        status    = "Low"
    elif avg_value_idr < _IDR_VAL_MODEST:
        status = "Modest"
    else:
        status = "Pass"

    return {
        "grade_cap"    : grade_cap,
        "penalty"      : penalty,
        "status"       : status,
        "avg_value_idr": round(avg_value_idr),
        "warnings"     : warnings,
    }


# ── Shared batch scan helper ──────────────────────────────────────────────────

def _batch_scan_idx(
    index_filter: str = "",
    timeframe:    str = "1D",
) -> List[dict]:
    """
    Batch scan IDX symbols via tradingview_ta.

    Returns list of dicts: {symbol, indicators, change_pct}
    Used by screen_idx_stocks, analyze_idx_index, and scan_by_signal.
    """
    if not _TA_AVAILABLE:
        return []

    if index_filter:
        idx_key = index_filter.strip().upper()
        symbols = IDX_INDICES[idx_key]["get_symbols"]() if idx_key in IDX_INDICES else []
    else:
        symbols = load_symbols("idx")

    if not symbols:
        return []

    results: List[dict] = []
    batch_size = 200

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = _get_multiple_analysis(
                screener=_IDX_SCREENER,
                interval=timeframe,
                symbols=batch,
            )
        except Exception:
            continue

        present = [sym for sym, data in analysis.items() if data is not None]
        atr_map: dict = {}
        if present:
            try:
                atr_map = fetch_atr_for_tickers(present, _IDX_SCREENER, timeframe)
            except Exception:
                pass

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                if ind.get("ATR") is None and sym in atr_map:
                    ind["ATR"] = atr_map[sym]
                o = ind.get("open")
                c = ind.get("close")
                if not o or not c or o <= 0:
                    continue
                results.append({
                    "symbol":     sym,
                    "indicators": ind,
                    "change_pct": ((c - o) / o) * 100,
                })
            except Exception:
                continue

    return results


# ── IDX Top Gainers / Losers ───────────────────────────────────────────────────

_TF_TO_TV: dict = {
    "1D": "1D", "1W": "1W", "1M": "1M",
    "4H": "240", "4h": "240",
    "1H": "60",  "1h": "60",
    "15m": "15", "5m": "5",
}


def get_idx_top_gainers(
    timeframe:      str   = "1D",
    limit:          int   = 30,
    min_change_pct: float = 0.0,
    min_volume_idr: float = 0.0,
    mode:           str   = "gainers",
    index_filter:   str   = "",
) -> dict:
    """
    Full-universe IDX top gainers/losers (~866 saham) via tradingview-screener Query.

    Menggunakan Query API langsung (bukan coinlist) sehingga mencakup SELURUH IDX
    termasuk saham kecil/mid-cap yang sering jadi top movers.

    Args:
        timeframe:      1D (default), 1W, 4H, 1H, 15m
        limit:          Max hasil (max 100)
        min_change_pct: Filter minimum % change (0 = semua)
        min_volume_idr: Filter minimum nilai transaksi dalam IDR (raw, bukan juta)
        mode:           "gainers" | "losers"
        index_filter:   LQ45, IDX30, IDX80, KOMPAS100, dll (kosong = semua IDX)
    """
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import Column
    except ImportError:
        return {"error": "tradingview-screener tidak tersedia. Jalankan: uv sync"}

    suffix = _TF_TO_TV.get(timeframe, "1D")

    def _c(name: str) -> str:
        """Tambahkan suffix timeframe ke nama kolom (jika bukan 1D)."""
        return f"{name}|{suffix}" if suffix != "1D" else name

    cols = [
        _c("open"), _c("close"), _c("volume"),
        _c("RSI"), _c("EMA20"), _c("EMA50"), _c("EMA200"),
        _c("change"),
        "name", "sector", "industry",
    ]

    # Build query — scan seluruh IDX market
    ascending = (mode == "losers")
    q = (Query()
         .set_markets("indonesia")
         .select(*cols)
         .order_by(_c("change"), ascending=ascending)
         .limit(1000))

    # Batasi ke konstituen index tertentu jika diminta
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

    try:
        total, df = q.get_scanner_data()
    except Exception as exc:
        return {"error": f"Gagal fetch data: {exc}"}

    if df is None or df.empty:
        return {"error": "Tidak ada data dari IDX"}

    # Normalize kolom: hapus suffix (mis "close|240" → "close")
    df.rename(columns=lambda c: c.split("|")[0] if isinstance(c, str) else c, inplace=True)

    results: List[dict] = []

    for _, row in df.iterrows():
        sym    = str(row.get("ticker", ""))
        close  = row.get("close") or 0
        open_  = row.get("open")  or 0
        vol    = row.get("volume") or 0
        change = row.get("change") or 0
        vol_idr = vol * close

        # Filter volume
        if min_volume_idr > 0 and vol_idr < min_volume_idr:
            continue
        # Filter change
        if mode == "gainers" and change < min_change_pct:
            continue
        if mode == "losers" and change > -abs(min_change_pct):
            continue

        ticker = sym.replace("IDX:", "")
        ema20  = row.get("EMA20")
        ema50  = row.get("EMA50")
        ema200 = row.get("EMA200")
        rsi    = row.get("RSI")

        ma_pos_parts = []
        if ema20  and close > ema20:  ma_pos_parts.append("↑EMA20")
        if ema50  and close > ema50:  ma_pos_parts.append("↑EMA50")
        if ema200 and close > ema200: ma_pos_parts.append("↑EMA200")

        # Sektor: pakai langsung dari TV screener, fallback ke static map
        sector = str(row.get("sector") or get_sector_label(ticker))

        results.append({
            "ticker"    : ticker,
            "name"      : str(row.get("name", "")),
            "price"     : round(close),
            "change_pct": round(change, 2),
            "volume_idr": round(vol_idr / 1_000_000, 1),
            "rsi"       : round(rsi, 1) if rsi else None,
            "ma_pos"    : " ".join(ma_pos_parts) if ma_pos_parts else "below all MA",
            "sector"    : sector,
        })

    limit = max(1, min(limit, 100))

    return {
        "mode"         : mode,
        "timeframe"    : timeframe,
        "index_filter" : index_filter or "All IDX",
        "total_scanned": total,
        "total_passed" : len(results),
        "results"      : results[:limit],
    }


# ── Stock Screener ─────────────────────────────────────────────────────────────

def screen_idx_stocks(
    timeframe:    str = "1D",
    min_score:    int = 55,
    index_filter: str = "",
    limit:        int = 20,
) -> dict:
    """
    Production stock ranking engine untuk IDX.

    Proses:
      1. Load symbols (dari index_filter atau coinlist/idx.txt)
      2. Batch scan via tradingview_ta (screener=indonesia)
      3. Hitung pct_rank inline dari batch yang sama (bukan scan terpisah)
      4. Score setiap saham, filter by min_score
      5. Compute trade setup & quality untuk saham score ≥ 70
      6. Return: qualified_trades, watchlist, grade_distribution

    Args:
        timeframe   : Interval TradingView — 1D (default), 1W, 4H, 1H
        min_score   : Minimum stock score (0-100, default 55)
        index_filter: Filter ke index tertentu — LQ45, IDX30, IDX80,
                      KOMPAS100, JII, IDXHIDIV20, IDXBUMN20
        limit       : Jumlah hasil maksimal (max 50)
    """
    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta tidak tersedia. Jalankan: uv sync"}

    # ── 1. Load symbols ────────────────────────────────────────────────────────
    if index_filter:
        idx_key = index_filter.strip().upper()
        if idx_key in IDX_INDICES:
            symbols      = IDX_INDICES[idx_key]["get_symbols"]()
            source_label = idx_key
        else:
            return {
                "error"    : f"Index tidak dikenal: {index_filter}",
                "available": list(IDX_INDICES.keys()),
            }
    else:
        symbols      = load_symbols("idx")
        source_label = "All IDX"

    if not symbols:
        return {"error": "Tidak ada simbol IDX ditemukan."}

    # ── 2. Batch scan ──────────────────────────────────────────────────────────
    raw_results: List[tuple] = []  # (sym, ind, change_pct)
    batch_size = 200

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = _get_multiple_analysis(
                screener=_IDX_SCREENER,
                interval=timeframe,
                symbols=batch,
            )
        except Exception:
            continue

        # Backfill ATR untuk batch ini
        present = [sym for sym, data in analysis.items() if data is not None]
        atr_map: dict = {}
        if present:
            try:
                atr_map = fetch_atr_for_tickers(present, _IDX_SCREENER, timeframe)
            except Exception:
                pass

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                if ind.get("ATR") is None and sym in atr_map:
                    ind["ATR"] = atr_map[sym]
                o = ind.get("open")
                c = ind.get("close")
                if not o or not c or o <= 0:
                    continue
                raw_results.append((sym, ind, ((c - o) / o) * 100))
            except Exception:
                continue

    if not raw_results:
        return {"error": "Tidak ada data dari IDX", "timeframe": timeframe}

    # ── 3. Pct_rank inline ─────────────────────────────────────────────────────
    changes = sorted([r[2] for r in raw_results])
    n       = len(changes)

    def _pct_rank(val: float) -> float:
        return sum(1 for c in changes if c < val) / n if n > 0 else 0.5

    # ── 4. Score + filter ──────────────────────────────────────────────────────
    scored_stocks: List[dict] = []

    for sym, ind, change in raw_results:
        try:
            close   = ind.get("close") or 0
            # volume.SMA20 tidak tersedia di Indonesia screener → fallback ke volume harian
            avg_vol = ind.get("volume.SMA20") or ind.get("volume")
            liq     = _idr_liquidity_check(avg_vol, close)

            # Skip saham dengan likuiditas sangat rendah jika min_score ≥ 55
            if liq["status"] == "Fail — Sangat Rendah" and min_score >= 55:
                continue

            pct_rank   = _pct_rank(change)
            # Semua IDX saham = IDR, tapi compute_stock_score pakai USD threshold
            # (lebih rendah) supaya volume check tetap realistis di skala USD
            result = compute_stock_score(ind, change_pct_rank=pct_rank, currency="USD")
            if not result:
                continue

            # Terapkan IDR liquidity penalty
            adj_score = max(0, result["score"] - liq["penalty"])
            if adj_score < min_score:
                continue

            metrics = compute_metrics(ind)
            if not metrics:
                continue

            clean_sym = sym.replace("IDX:", "")
            entry: dict = {
                "symbol"         : sym,
                "ticker"         : clean_sym,
                "sector"         : get_sector_label(clean_sym),
                "is_lq45"        : sym in (IDX_INDICES["LQ45"]["get_symbols"]()),
                "price"          : metrics["price"],
                "stock_score"    : adj_score,
                "raw_score"      : result["score"],
                "grade"          : result["grade"],
                "trend_state"    : result["trend_state"],
                "change_pct"     : result["change_pct"],
                "pct_rank"       : round(pct_rank, 3),
                "score_breakdown": result["breakdown"],
                "signals"        : result["signals"],
                "penalties"      : result["penalties"],
                "liquidity"      : {
                    "status"       : liq["status"],
                    "avg_value_idr": liq.get("avg_value_idr"),
                    "warnings"     : liq["warnings"],
                },
            }

            # Trade setup untuk saham dengan score cukup tinggi
            if adj_score >= 70:
                setup = compute_trade_setup(ind)
                if setup:
                    quality = compute_trade_quality(ind, adj_score, setup)
                    entry["trade_setup"] = {
                        "setup_types"      : setup["setup_types"],
                        "entry_points"     : setup["entry_points"],
                        "stop_loss"        : setup["stop_loss"],
                        "stop_distance_pct": setup["stop_distance_pct"],
                        "targets"          : setup["targets"],
                        "risk_reward"      : setup["risk_reward"],
                        "supports"         : setup["supports"],
                        "resistances"      : setup["resistances"],
                    }
                    entry["trade_quality_score"] = quality["trade_quality_score"]
                    entry["trade_quality"]       = quality["quality"]
                    entry["trade_notes"]         = quality["notes"]
                    entry["trade_quality_breakdown"] = quality["breakdown"]

            scored_stocks.append(entry)
        except Exception:
            continue

    # ── 5. Sort & split ────────────────────────────────────────────────────────
    scored_stocks.sort(
        key=lambda x: (x["stock_score"], x.get("trade_quality_score", 0)),
        reverse=True,
    )

    grades: Dict[str, int] = {}
    for s in scored_stocks:
        g = s["grade"]
        grades[g] = grades.get(g, 0) + 1

    qualified = [
        s for s in scored_stocks
        if s["stock_score"] >= 70 and s.get("trade_quality_score", 0) >= 65
    ]
    watchlist = [
        s for s in scored_stocks
        if s["stock_score"] < 70 or s.get("trade_quality_score", 0) < 65
    ]

    return {
        "source"            : source_label,
        "timeframe"         : timeframe,
        "min_score"         : min_score,
        "total_scanned"     : len(raw_results),
        "total_passed"      : len(scored_stocks),
        "grade_distribution": grades,
        "qualified_trades"  : qualified[:limit],
        "qualified_count"   : len(qualified),
        "watchlist"         : watchlist[: max(5, limit - len(qualified))],
        "execution_rules"   : {
            "trade_threshold"  : "Stock Score ≥ 70 DAN Trade Quality ≥ 65",
            "liquidity_min"    : "≥ 100M IDR/hari (disarankan ≥ 2B IDR/hari)",
            "risk_reward_min"  : "R:R ke Target 2 ≥ 2.0 direkomendasikan",
            "disclaimer"       : "Untuk tujuan edukasi/informasi saja. Bukan saran investasi.",
        },
    }


# ── Index Analysis ─────────────────────────────────────────────────────────────

def analyze_idx_index(
    index:     str = "LQ45",
    timeframe: str = "1D",
    limit:     int = 45,
) -> dict:
    """
    Analisis sebuah IDX index — performa konstituen, breadth, dan sektor.

    Menampilkan:
      - Index stats: advancing/declining/unchanged, avg change, breadth, sentimen
      - Sector breakdown: ranked by avg change
      - Top 5 gainers & top 5 losers
      - Detail semua saham (limited by `limit`)

    Args:
        index     : LQ45 (default), IDX30, IDX80, KOMPAS100, JII, IDXHIDIV20, IDXBUMN20
        timeframe : Interval TradingView — 1D, 1W, 4H, 1H
        limit     : Jumlah saham yang ditampilkan detail (max 100)
    """
    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta tidak tersedia. Jalankan: uv sync"}

    index_key = index.strip().upper()
    if index_key not in IDX_INDICES:
        return {
            "error"            : f"Index tidak dikenal: {index}",
            "available_indices": list(IDX_INDICES.keys()),
            "usage"            : "Gunakan LQ45, IDX30, IDX80, KOMPAS100, JII, IDXHIDIV20, atau IDXBUMN20",
        }

    index_info = IDX_INDICES[index_key]
    symbols    = index_info["get_symbols"]()

    # ── Batch scan ─────────────────────────────────────────────────────────────
    all_stocks: List[dict] = []
    batch_size = 200

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = _get_multiple_analysis(
                screener=_IDX_SCREENER,
                interval=timeframe,
                symbols=batch,
            )
        except Exception:
            continue

        # Backfill ATR
        present = [sym for sym, data in analysis.items() if data is not None]
        atr_map: dict = {}
        if present:
            try:
                atr_map = fetch_atr_for_tickers(present, _IDX_SCREENER, timeframe)
            except Exception:
                pass

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                if ind.get("ATR") is None and sym in atr_map:
                    ind["ATR"] = atr_map[sym]

                metrics = compute_metrics(ind)
                if not metrics:
                    continue

                extended = extract_extended_indicators(ind)
                close    = ind.get("close") or 0
                open_p   = ind.get("open")
                chg      = ((close - open_p) / open_p * 100) if open_p and open_p > 0 else 0

                clean_sym = sym.replace("IDX:", "")
                all_stocks.append({
                    "symbol"         : sym,
                    "ticker"         : clean_sym,
                    "sector"         : get_sector_label(clean_sym),
                    "is_lq45"        : is_lq45(sym, index_key),
                    "price"          : metrics.get("price", 0),
                    "change_pct"     : round(chg, 2),
                    "volume"         : ind.get("volume", 0),
                    "rsi"            : extended["rsi"]["value"],
                    "rsi_signal"     : extended["rsi"]["signal"],
                    "sma20"          : extended["sma"]["sma20"],
                    "sma50"          : extended["sma"]["sma50"],
                    "sma200"         : extended["sma"]["sma200"],
                    "atr"            : extended["atr"]["value"],
                    "atr_volatility" : extended["atr"]["volatility"],
                    "macd_crossover" : extended["macd"]["crossover"],
                    "volume_signal"  : extended["volume"]["signal"],
                    "bbw"            : metrics.get("bbw", 0),
                    "bb_signal"      : metrics.get("signal", "N/A"),
                })
            except Exception:
                continue

    if not all_stocks:
        return {
            "error"    : f"Tidak ada data untuk konstituen {index_key}",
            "timeframe": timeframe,
        }

    # ── Hitung stats ────────────────────────────────────────────────────────────
    changes   = [s["change_pct"] for s in all_stocks]
    avg_change = sum(changes) / len(changes) if changes else 0
    advancing  = sum(1 for c in changes if c > 0)
    declining  = sum(1 for c in changes if c < 0)
    unchanged  = sum(1 for c in changes if c == 0)

    # ── Sector breakdown ────────────────────────────────────────────────────────
    sector_perf: Dict[str, Any] = {}
    for s in all_stocks:
        sec = s["sector"]
        if sec not in sector_perf:
            sector_perf[sec] = {"stocks": 0, "total_change": 0.0}
        sector_perf[sec]["stocks"]       += 1
        sector_perf[sec]["total_change"] += s["change_pct"]

    sector_summary = sorted(
        [
            {
                "sector"      : sec,
                "stocks_count": d["stocks"],
                "avg_change"  : round(d["total_change"] / d["stocks"], 2),
            }
            for sec, d in sector_perf.items()
        ],
        key=lambda x: x["avg_change"],
        reverse=True,
    )

    by_change = sorted(all_stocks, key=lambda x: x["change_pct"], reverse=True)

    return {
        "index"       : index_key,
        "index_name"  : index_info["name"],
        "description" : index_info["description"],
        "timeframe"   : timeframe,

        "index_stats" : {
            "total_constituents": index_info["constituents_count"],
            "analyzed"          : len(all_stocks),
            "avg_change"        : round(avg_change, 2),
            "advancing"         : advancing,
            "declining"         : declining,
            "unchanged"         : unchanged,
            "breadth_pct"       : round(advancing / len(all_stocks) * 100, 1) if all_stocks else 0,
            "sentiment"         : (
                "Bullish"  if avg_change >  0.5 else
                "Bearish"  if avg_change < -0.5 else
                "Neutral"
            ),
        },

        "sector_breakdown": sector_summary,
        "top_gainers"     : by_change[:5],
        "top_losers"      : by_change[-5:][::-1],
        "all_stocks"      : by_change[:limit],
    }


def is_lq45(sym: str, current_index: str) -> bool:
    """True jika saham ada di LQ45 (independen dari index yang sedang dianalisa)."""
    lq45 = IDX_INDICES["LQ45"]["get_symbols"]()
    return sym in lq45
