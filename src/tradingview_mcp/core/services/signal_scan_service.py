"""
Signal-based scanner untuk IDX.

Scan saham IDX berdasarkan sinyal teknikal spesifik:
  golden_cross, death_cross, rsi_oversold, rsi_overbought,
  macd_bullish, macd_bearish, bollinger_squeeze,
  volume_spike, above_ema20, below_ema20,
  ema_stack_bullish, ema_stack_bearish

Source: TradingView screener (tradingview_ta, screener="indonesia")
"""
from __future__ import annotations

from typing import Optional

from tradingview_mcp.core.services.idx_screener_service import (
    _batch_scan_idx,
    _IDR_VAL_FLOOR,
)

# ── Signal Definitions ────────────────────────────────────────────────────────

AVAILABLE_SIGNALS = {
    "golden_cross":      "EMA50 crosses above EMA200 (bullish long-term)",
    "death_cross":       "EMA50 crosses below EMA200 (bearish long-term)",
    "ema_stack_bullish": "Price > EMA20 > EMA50 > EMA200 (full bull stack)",
    "ema_stack_bearish": "Price < EMA20 < EMA50 < EMA200 (full bear stack)",
    "above_ema20":       "Price above EMA20 (short-term bullish bias)",
    "below_ema20":       "Price below EMA20 (short-term bearish bias)",
    "rsi_oversold":      "RSI < 35 (potential reversal zone)",
    "rsi_overbought":    "RSI > 70 (extended, watch for pullback)",
    "rsi_neutral":       "RSI 40–60 (consolidating, no extremes)",
    "macd_bullish":      "MACD line above signal line + histogram rising",
    "macd_bearish":      "MACD line below signal line + histogram falling",
    "bollinger_squeeze": "Bollinger Band width < 0.1 (low volatility, breakout incoming)",
    "volume_spike":      "Today's volume > 2x average (unusual activity)",
    "near_resistance":   "Price within 2% of nearest resistance (R1 pivot)",
    "near_support":      "Price within 2% of nearest support (S1 pivot)",
    "tv_buy":            "TradingView rating >= BUY (recommendation >= 0.2)",
    "tv_strong_buy":     "TradingView rating >= STRONG BUY (recommendation >= 0.5)",
    "tv_sell":           "TradingView rating <= SELL (recommendation <= -0.2)",
}

# ── Signal Evaluators ─────────────────────────────────────────────────────────

def _evaluate_signal(signal: str, ind: dict, close: float) -> bool:
    """Return True if the indicator data matches the given signal."""
    e10  = ind.get("EMA10",  ind.get("EMA[10]", None))
    e20  = ind.get("EMA20",  ind.get("EMA[20]", None))
    e50  = ind.get("EMA50",  ind.get("EMA[50]", None))
    e200 = ind.get("EMA200", ind.get("EMA[200]", None))
    rsi  = ind.get("RSI",    ind.get("RSI[14]", None))
    macd = ind.get("MACD.macd", None)
    macd_sig = ind.get("MACD.signal", None)
    macd_hist = ind.get("MACD.hist", None)
    bb_upper = ind.get("BB.upper", None)
    bb_lower = ind.get("BB.lower", None)
    volume   = ind.get("volume", None)
    vol_sma  = ind.get("volume.SMA20", volume)  # fallback
    rec      = ind.get("Recommend.All", None)
    pivot_r1 = ind.get("Pivot.M.Classic.R1", None)
    pivot_s1 = ind.get("Pivot.M.Classic.S1", None)

    try:
        if signal == "golden_cross":
            return e50 is not None and e200 is not None and e50 > e200
        if signal == "death_cross":
            return e50 is not None and e200 is not None and e50 < e200
        if signal == "ema_stack_bullish":
            return (e20 and e50 and e200 and
                    close > e20 > e50 > e200)
        if signal == "ema_stack_bearish":
            return (e20 and e50 and e200 and
                    close < e20 < e50 < e200)
        if signal == "above_ema20":
            return e20 is not None and close > e20
        if signal == "below_ema20":
            return e20 is not None and close < e20
        if signal == "rsi_oversold":
            return rsi is not None and rsi < 35
        if signal == "rsi_overbought":
            return rsi is not None and rsi > 70
        if signal == "rsi_neutral":
            return rsi is not None and 40 <= rsi <= 60
        if signal == "macd_bullish":
            return (macd is not None and macd_sig is not None and
                    macd > macd_sig and (macd_hist or 0) > 0)
        if signal == "macd_bearish":
            return (macd is not None and macd_sig is not None and
                    macd < macd_sig and (macd_hist or 0) < 0)
        if signal == "bollinger_squeeze":
            if bb_upper and bb_lower and close > 0:
                bw = (bb_upper - bb_lower) / close
                return bw < 0.10
            return False
        if signal == "volume_spike":
            if volume and vol_sma and vol_sma > 0:
                return volume > vol_sma * 2.0
            return False
        if signal == "near_resistance":
            if pivot_r1 and close > 0:
                return abs(pivot_r1 - close) / close < 0.02
            return False
        if signal == "near_support":
            if pivot_s1 and close > 0:
                return abs(pivot_s1 - close) / close < 0.02
            return False
        if signal == "tv_buy":
            return rec is not None and rec >= 0.2
        if signal == "tv_strong_buy":
            return rec is not None and rec >= 0.5
        if signal == "tv_sell":
            return rec is not None and rec <= -0.2
    except (TypeError, ZeroDivisionError):
        pass
    return False


# ── Main Scanner ──────────────────────────────────────────────────────────────

def scan_by_signal(
    signal: str,
    timeframe: str = "1D",
    index_filter: str = "",
    limit: int = 20,
    min_liquidity_idr: float = _IDR_VAL_FLOOR,
) -> dict:
    """
    Scan saham IDX yang memenuhi sinyal teknikal tertentu.

    Args:
        signal:            Nama sinyal (lihat AVAILABLE_SIGNALS)
        timeframe:         Timeframe analisis (1D, 1W, 4H, 1H, 15m)
        index_filter:      Filter ke index tertentu (LQ45, IDX30, IDX80, dll)
        limit:             Max hasil yang dikembalikan
        min_liquidity_idr: Minimum nilai transaksi harian IDR

    Returns:
        dict dengan matched_stocks, signal_info, scan_stats
    """
    signal = signal.lower().strip()

    if signal not in AVAILABLE_SIGNALS:
        return {
            "success": False,
            "error": f"Signal '{signal}' tidak dikenal.",
            "available_signals": list(AVAILABLE_SIGNALS.keys()),
            "signal_descriptions": AVAILABLE_SIGNALS,
        }

    # Batch scan via idx_screener_service helper (TA check ada di dalam _batch_scan_idx)
    batch = _batch_scan_idx(index_filter=index_filter, timeframe=timeframe)
    if not batch:
        return {"success": False, "error": "Batch scan gagal atau tidak ada data"}

    matched = []
    skipped_liquidity = 0

    for item in batch:
        sym   = item["symbol"]
        ind   = item["indicators"]
        close = ind.get("close", 0) or 0

        # Liquidity gate
        vol = ind.get("volume.SMA20") or ind.get("volume") or 0
        avg_val = vol * close
        if avg_val < min_liquidity_idr:
            skipped_liquidity += 1
            continue

        if not _evaluate_signal(signal, ind, close):
            continue

        # Build result row
        rsi   = ind.get("RSI", ind.get("RSI[14]"))
        macd  = ind.get("MACD.macd")
        msig  = ind.get("MACD.signal")
        e20   = ind.get("EMA20")
        e50   = ind.get("EMA50")
        e200  = ind.get("EMA200")
        rec   = ind.get("Recommend.All")
        chg   = ind.get("change", 0) or 0
        vol_raw = ind.get("volume", 0) or 0

        rec_label = "—"
        if rec is not None:
            if rec >= 0.5:   rec_label = "Strong Buy"
            elif rec >= 0.2: rec_label = "Buy"
            elif rec >= -0.2: rec_label = "Neutral"
            elif rec >= -0.5: rec_label = "Sell"
            else:             rec_label = "Strong Sell"

        matched.append({
            "symbol": sym,
            "close": close,
            "change_pct": round(chg, 2),
            "avg_value_idr_b": round(avg_val / 1e9, 2),
            "rsi": round(rsi, 1) if rsi else None,
            "macd_above_signal": (macd > msig) if (macd and msig) else None,
            "ema20": round(e20, 0) if e20 else None,
            "ema50": round(e50, 0) if e50 else None,
            "ema200": round(e200, 0) if e200 else None,
            "tv_rating": rec_label,
            "volume": int(vol_raw),
        })

    # Sort by avg value IDR descending (most liquid first)
    matched.sort(key=lambda x: x["avg_value_idr_b"], reverse=True)
    matched = matched[:limit]

    return {
        "success": True,
        "signal": signal,
        "signal_description": AVAILABLE_SIGNALS[signal],
        "timeframe": timeframe,
        "index_filter": index_filter or "ALL IDX",
        "scan_stats": {
            "total_scanned": len(batch),
            "skipped_low_liquidity": skipped_liquidity,
            "matched": len(matched),
        },
        "matched_stocks": matched,
    }
