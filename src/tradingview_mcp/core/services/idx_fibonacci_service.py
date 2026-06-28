"""
IDX Fibonacci Retracement & Extension Analysis.

Port dari egx_fibonacci_retracement tapi untuk Bursa Efek Indonesia (IDX).

Sumber swing high/low (priority order):
  1. tradingview-screener: kolom 52W high/low, 6M, 3M, 1M
  2. Fallback: pivot R3/S3 dari tradingview_ta
  3. Fallback: yfinance historical data untuk hitung high/low langsung

Output:
  - 7 retracement levels (0% – 100%)
  - 3 extension levels (127.2%, 161.8%, 261.8%)
  - Price position (zona, nearest level, fib supports/resistances)
  - Context: RSI, EMA50, EMA200, ATR, volume ratio
"""
from __future__ import annotations

import re
from typing import Optional

import requests as _requests

# ── tradingview_ta ─────────────────────────────────────────────────────────────
try:
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as _get_multiple_analysis,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

# ── yfinance (fallback untuk high/low) ────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

_TV_SCAN_URL = "https://scanner.tradingview.com/indonesia/scan"
_TV_HEADERS  = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

from tradingview_mcp.core.services.indicators import (
    compute_fibonacci_levels,
    analyze_fibonacci_position,
    detect_trend_for_fibonacci,
    _safe_round,
)

_IDX_SCREENER = "indonesia"

# Mapping lookback → (tv_scan_col_high, tv_scan_col_low, yf_period)
# Kolom ini valid di indonesia/scan endpoint (bukan via tradingview-screener library)
_LOOKBACK_MAP = {
    "1M":  ("High.1M",            "Low.1M",            "1mo"),
    "3M":  ("High.3M",            "Low.3M",            "3mo"),
    "6M":  ("High.6M",            "Low.6M",            "6mo"),
    "52W": ("price_52_week_high", "price_52_week_low",  "1y"),
    "ALL": ("High.All",           "Low.All",            "max"),
}


def _clean_ticker(ticker: str) -> str:
    return re.sub(r"\.JK$", "", ticker.strip().upper())


def _yf_ticker(ticker: str) -> str:
    t = _clean_ticker(ticker)
    return f"{t}.JK"


def _fetch_swing_from_scanner(
    full_symbol: str,
    high_col: str,
    low_col: str,
) -> tuple[Optional[float], Optional[float], str]:
    """
    Ambil swing high/low langsung dari indonesia/scan endpoint.
    Bypass tradingview-screener library karena kolom period (High.6M, dll)
    hanya valid di market-specific endpoint, bukan global/scan.
    """
    try:
        resp = _requests.post(
            _TV_SCAN_URL,
            json={
                "symbols": {"tickers": [full_symbol], "query": {"types": []}},
                "columns": [high_col, low_col],
            },
            headers=_TV_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None, None, ""
        rows = resp.json().get("data", [])
        if not rows:
            return None, None, ""
        d = rows[0].get("d", [None, None])
        h, lo = d[0], d[1]
        if h is not None and lo is not None:
            h, lo = float(h), float(lo)
            if h > lo and h > 0 and lo > 0:
                return h, lo, f"TV scanner ({high_col}/{low_col})"
    except Exception:
        pass
    return None, None, ""


def _fetch_swing_from_yfinance(
    ticker: str, period: str
) -> tuple[Optional[float], Optional[float], str]:
    """Fallback: hitung high/low dari yfinance OHLCV."""
    if not _YF_AVAILABLE:
        return None, None, ""
    try:
        hist = yf.download(_yf_ticker(ticker), period=period,
                           interval="1d", progress=False, auto_adjust=True)
        if hist is None or len(hist) < 5:
            return None, None, ""
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        h  = float(hist["High"].max())
        lo = float(hist["Low"].min())
        if h > lo:
            return h, lo, f"yfinance ({period} OHLCV)"
    except Exception:
        pass
    return None, None, ""


def analyze_idx_fibonacci(
    ticker: str,
    lookback: str = "52W",
    timeframe: str = "1D",
) -> dict:
    """
    Fibonacci retracement & extension analysis untuk saham IDX.

    Args:
        ticker   : Kode saham IDX (contoh: "BBCA", "TLKM", "ZATA")
        lookback : Periode swing high/low — "1M", "3M", "6M", "52W" (default), "ALL"
        timeframe: TradingView interval untuk TA data — "1D" (default), "1W", "4H"

    Returns:
        Dict lengkap: levels, price position, context, interpretation.
    """
    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta tidak tersedia. Jalankan: uv sync"}

    valid_lookbacks = set(_LOOKBACK_MAP.keys())
    if lookback not in valid_lookbacks:
        return {
            "error": f"Lookback tidak valid: {lookback}",
            "valid": sorted(valid_lookbacks),
        }

    clean       = _clean_ticker(ticker)
    full_symbol = f"IDX:{clean}"
    tf          = timeframe.strip().upper() or "1D"
    high_col, low_col, yf_period = _LOOKBACK_MAP[lookback]

    # ── 1. Fetch TA data ───────────────────────────────────────────────────────
    try:
        analysis = _get_multiple_analysis(
            screener=_IDX_SCREENER,
            interval=tf,
            symbols=[full_symbol],
        )
    except Exception as exc:
        return {"error": f"Gagal fetch data TA: {exc}"}

    if full_symbol not in analysis or analysis[full_symbol] is None:
        return {"error": f"Tidak ada data untuk {full_symbol}. Pastikan ticker valid."}

    ind   = analysis[full_symbol].indicators
    close = ind.get("close")
    if not close or close <= 0:
        return {"error": f"Tidak ada data harga untuk {full_symbol}"}

    # Backfill ATR
    if ind.get("ATR") is None:
        try:
            from tradingview_mcp.core.services.screener_provider import fetch_atr_for_ticker
            atr_val = fetch_atr_for_ticker(full_symbol, _IDX_SCREENER, tf)
            if atr_val is not None:
                ind["ATR"] = atr_val
        except Exception:
            pass

    # ── 2. Swing high/low (priority: screener → pivot → yfinance) ─────────────
    swing_high: Optional[float] = None
    swing_low:  Optional[float] = None
    swing_source: str = ""

    # Priority 1: TV Scanner indonesia/scan endpoint (direct, paling akurat)
    swing_high, swing_low, swing_source = _fetch_swing_from_scanner(
        full_symbol, high_col, low_col
    )

    # Priority 2: Pivot R3/S3 dari tradingview_ta
    if swing_high is None:
        fib_r3     = ind.get("Pivot.M.Fibonacci.R3")
        fib_s3     = ind.get("Pivot.M.Fibonacci.S3")
        classic_r3 = ind.get("Pivot.M.Classic.R3")
        classic_s3 = ind.get("Pivot.M.Classic.S3")
        h_cand = fib_r3 or classic_r3
        l_cand = fib_s3 or classic_s3
        if h_cand and l_cand and h_cand > l_cand > 0:
            swing_high   = float(h_cand)
            swing_low    = float(l_cand)
            swing_source = "pivot R3/S3 (fallback)"

    # Priority 3: yfinance historical
    if swing_high is None:
        swing_high, swing_low, swing_source = _fetch_swing_from_yfinance(clean, yf_period)

    if swing_high is None or swing_low is None:
        return {
            "error": "Tidak bisa menentukan swing high/low untuk kalkulasi Fibonacci",
            "ticker": clean,
            "lookback": lookback,
            "hint": "Coba lookback lebih pendek (3M/1M) atau timeframe berbeda",
        }

    swing_range_pct = ((swing_high - swing_low) / swing_low) * 100
    if swing_range_pct < 2:
        return {
            "error": f"Swing range terlalu kecil ({swing_range_pct:.1f}%) untuk Fibonacci bermakna",
            "swing_high": round(swing_high, 0),
            "swing_low":  round(swing_low, 0),
        }

    # ── 3. Deteksi trend & hitung Fibonacci levels ─────────────────────────────
    ema50  = ind.get("EMA50")
    ema200 = ind.get("EMA200")
    trend, trend_reasoning = detect_trend_for_fibonacci(
        close, swing_high, swing_low, ema50, ema200
    )
    fib_levels = compute_fibonacci_levels(swing_high, swing_low, trend)
    position   = analyze_fibonacci_position(close, fib_levels)

    # ── 4. Context indicators ──────────────────────────────────────────────────
    rsi_val = ind.get("RSI")
    atr_val = ind.get("ATR")
    vol     = ind.get("volume")
    vol_sma = ind.get("volume.SMA20")
    vol_ratio = round(vol / vol_sma, 2) if vol and vol_sma and vol_sma > 0 else None

    open_p    = ind.get("open")
    change_pct = round(((close - open_p) / open_p) * 100, 2) if open_p else None

    # ── 5. Interpretation text ─────────────────────────────────────────────────
    parts = [
        f"Harga di {position['retracement_depth_pct']}% retracement dari {trend}."
    ]
    if position.get("key_zone"):
        parts.append(f"Berada di zona kunci: {position['key_zone']}.")
    if position.get("fib_supports"):
        ns = position["fib_supports"][0]
        parts.append(f"Support Fib terdekat: {ns['price']:,.0f} ({ns['ratio']}).")
    if position.get("fib_resistances"):
        nr = position["fib_resistances"][0]
        parts.append(f"Resistance Fib terdekat: {nr['price']:,.0f} ({nr['ratio']}).")
    if atr_val:
        atr_pct = (atr_val / close) * 100
        parts.append(f"ATR {atr_pct:.1f}% — "
                     + ("volatilitas normal." if atr_pct < 4 else
                        "volatilitas tinggi, perlebar stop." if atr_pct < 8 else
                        "SANGAT volatil, hati-hati sizing."))

    # ── 6. Trade context: jarak ke level kunci ─────────────────────────────────
    ret_levels = fib_levels.get("retracement_levels", {})
    key_levels = {}
    # Untuk uptrend: 0.0 = swing high, 1.0 = swing low (retracement dari atas)
    # Untuk downtrend: 0.0 = swing low, 1.0 = swing high (retracement dari bawah)
    _label_uptrend = {
        "0.0":   "swing high (puncak, 0% retracement)",
        "0.236": "Fib 23.6%",
        "0.382": "Fib 38.2% (golden zone start)",
        "0.5":   "Fib 50%",
        "0.618": "Fib 61.8% (golden pocket)",
        "0.786": "Fib 78.6%",
        "1.0":   "swing low (dasar, 100% retracement)",
    }
    _label_downtrend = {
        "0.0":   "swing low (dasar, 0% retracement)",
        "0.236": "Fib 23.6%",
        "0.382": "Fib 38.2% (golden zone start)",
        "0.5":   "Fib 50%",
        "0.618": "Fib 61.8% (golden pocket)",
        "0.786": "Fib 78.6%",
        "1.0":   "swing high (puncak, 100% retracement)",
    }
    _label_map = _label_uptrend if trend == "uptrend" else _label_downtrend

    for ratio_str, price in ret_levels.items():
        dist_pct = ((price - close) / close) * 100
        label = _label_map.get(ratio_str, f"Fib {ratio_str}")
        key_levels[ratio_str] = {
            "price"   : round(price, 0),
            "label"   : label,
            "dist_pct": round(dist_pct, 2),
            "direction": "resistance" if dist_pct > 0 else "support",
        }

    return {
        "ticker"        : clean,
        "exchange"      : "IDX",
        "timeframe"     : tf,
        "lookback"      : lookback,

        "price"         : round(close, 0),
        "change_pct"    : change_pct,

        "swing_high"    : round(swing_high, 0),
        "swing_low"     : round(swing_low, 0),
        "swing_range_pct": round(swing_range_pct, 1),
        "swing_source"  : swing_source,

        "trend"         : trend,
        "trend_reasoning": trend_reasoning,

        "retracement_levels": {
            k: round(v, 0) for k, v in ret_levels.items()
        },
        "extension_levels": {
            k: round(v, 0) for k, v in fib_levels.get("extension_levels", {}).items()
        },
        "key_levels"    : key_levels,

        "price_position": position,

        "context": {
            "rsi"         : round(rsi_val, 1) if rsi_val else None,
            "ema50"       : round(ema50, 0) if ema50 else None,
            "ema200"      : round(ema200, 0) if ema200 else None,
            "atr"         : round(atr_val, 0) if atr_val else None,
            "atr_pct"     : round((atr_val / close) * 100, 1) if atr_val and close else None,
            "volume_ratio": vol_ratio,
            "vol_vs_avg"  : (
                "Above avg" if vol_ratio and vol_ratio >= 1.2 else
                "Normal"    if vol_ratio and vol_ratio >= 0.8 else
                "Below avg" if vol_ratio else "N/A"
            ),
        },

        "interpretation": " ".join(parts),
        "disclaimer"    : "Untuk tujuan edukasi/informasi saja. Bukan saran investasi.",
    }
