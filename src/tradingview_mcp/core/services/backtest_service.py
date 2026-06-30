"""
Backtesting Service for tradingview-mcp — v4 (v0.8.0)

Pure Python — no pandas, no numpy, no external backtesting libraries.

Supported strategies (9 generic + 6 CIA-specific):
  Generic: rsi, bollinger, macd, ema_cross, supertrend, donchian,
           rsi_pullback, keltner_breakout, triple_ema
  CIA IDX: cia_superketat, cia_ketat, cia_kamehameha, cia_rainbow,
           cia_star, cia_sunflower

v0.8.0 additions (CIA-specific):
  - 6 CIA trading setup strategies (MA-based, IDX style)
  - ARA/ARB price limit simulation (IDX ±20% auto-rejection)
  - V60 (60-day average volume) for Kamehameha detection
  - IDX broker commission structure (buy/sell separate)
  - run_cia_backtest() public API
  - compare_cia_strategies() public API
"""
from __future__ import annotations

import json
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.indicators_calc import (
    calc_rsi, calc_bollinger, calc_macd, calc_ema, calc_sma, calc_atr,
    calc_supertrend, calc_donchian,
)

_UA       = "tradingview-mcp/0.7.0 backtest-bot"
_YF_BASE  = "https://query1.finance.yahoo.com/v8/finance/chart"

_VALID_PERIODS   = {"1mo", "3mo", "6mo", "1y", "2y"}
_VALID_INTERVALS = {"1d", "1h"}

# Annualization factor for Sharpe ratio
_ANNUALIZATION = {"1d": 252, "1h": 252 * 6}

_STRATEGY_LABELS = {
    "rsi":              "RSI Oversold/Overbought",
    "bollinger":        "Bollinger Band Mean Reversion",
    "macd":             "MACD Crossover",
    "ema_cross":        "EMA 20/50 Golden/Death Cross",
    "supertrend":       "Supertrend (ATR-based Trend Following)",
    "donchian":         "Donchian Channel Breakout",
    "rsi_pullback":     "RSI Pullback in Uptrend (SMA50>SMA200)",
    "keltner_breakout": "Keltner Channel Breakout (EMA20 + 2·ATR)",
    "triple_ema":       "EMA 20/50 Cross with SMA200 Trend Filter",
}

# Strategies that require SMA200 warmup → need ≥220 bars to produce signals
_SMA200_STRATEGIES = {"rsi_pullback", "triple_ema"}
_SMA200_MIN_BARS  = 220


# ─── Data Fetching ────────────────────────────────────────────────────────────

def _fetch_ohlcv(symbol: str, period: str, interval: str = "1d") -> list[dict]:
    url = f"{_YF_BASE}/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})

    data = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass

    if data is None:
        try:
            from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy
            opener = build_opener_with_proxy(_UA)
            with opener.open(url, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Both direct and proxy connections failed: {e}")

    result     = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q          = result["indicators"]["quote"][0]
    date_fmt   = "%Y-%m-%d %H:%M" if interval == "1h" else "%Y-%m-%d"

    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date":   datetime.fromtimestamp(ts, tz=timezone.utc).strftime(date_fmt),
            "open":   round(o, 4),
            "high":   round(h, 4),
            "low":    round(l, 4),
            "close":  round(c, 4),
            "volume": v or 0,
        })
    return candles


# ─── Strategy Engines ─────────────────────────────────────────────────────────

def _run_rsi(candles, oversold=40, overbought=60, period=14, **_):
    closes = [c["close"] for c in candles]
    rsi    = calc_rsi(closes, period)
    trades, position = [], None
    for i in range(1, len(candles)):
        if rsi[i] is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        if position is None and rsi[i] < oversold:
            position = {"entry_date": date, "entry_price": price, "strategy": "rsi"}
        elif position is not None and rsi[i] > overbought:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_bollinger(candles, period=20, std_mult=2.0, **_):
    closes = [c["close"] for c in candles]
    bb     = calc_bollinger(closes, period, std_mult)
    trades, position = [], None
    for i in range(1, len(candles)):
        if bb["lower"][i] is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        if position is None and price < bb["lower"][i]:
            position = {"entry_date": date, "entry_price": price, "strategy": "bollinger"}
        elif position is not None and price > bb["middle"][i]:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_macd(candles, fast=12, slow=26, signal=9, **_):
    closes = [c["close"] for c in candles]
    macd   = calc_macd(closes, fast, slow, signal)
    trades, position = [], None
    for i in range(1, len(candles)):
        m, s, mp, sp = macd["macd"][i], macd["signal"][i], macd["macd"][i-1], macd["signal"][i-1]
        if None in (m, s, mp, sp):
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        if position is None and mp < sp and m >= s:
            position = {"entry_date": date, "entry_price": price, "strategy": "macd"}
        elif position is not None and mp > sp and m <= s:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_ema_cross(candles, fast_period=20, slow_period=50, **_):
    closes   = [c["close"] for c in candles]
    ema_fast = calc_ema(closes, fast_period)
    ema_slow = calc_ema(closes, slow_period)
    trades, position = [], None
    for i in range(1, len(candles)):
        f, s, fp, sp = ema_fast[i], ema_slow[i], ema_fast[i-1], ema_slow[i-1]
        if None in (f, s, fp, sp):
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        if position is None and fp < sp and f >= s:
            position = {"entry_date": date, "entry_price": price, "strategy": "ema_cross"}
        elif position is not None and fp > sp and f <= s:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_supertrend(candles, atr_period=10, multiplier=3.0, **_):
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]
    st     = calc_supertrend(highs, lows, closes, atr_period, multiplier)
    trades, position = [], None
    for i in range(1, len(candles)):
        d, dp = st["direction"][i], st["direction"][i - 1]
        if d is None or dp is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        if position is None and dp == -1 and d == 1:
            position = {"entry_date": date, "entry_price": price, "strategy": "supertrend"}
        elif position is not None and dp == 1 and d == -1:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_donchian(candles, period=20, **_):
    highs  = [c["high"] for c in candles]
    lows   = [c["low"]  for c in candles]
    dc     = calc_donchian(highs, lows, period)
    trades, position = [], None
    for i in range(1, len(candles)):
        if dc["upper"][i] is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        prev_high   = highs[i - 1]
        if position is None and dc["upper"][i - 1] is not None and prev_high > dc["upper"][i - 1]:
            position = {"entry_date": date, "entry_price": price, "strategy": "donchian"}
        elif position is not None and dc["lower"][i] is not None and price < dc["lower"][i]:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_rsi_pullback(candles, rsi_period=14, oversold=40, overbought=70,
                       fast_ma=50, slow_ma=200, **_):
    """Dip-buy in confirmed uptrend.

    Entry: SMA(fast_ma) > SMA(slow_ma)  AND  RSI < oversold
    Exit:  RSI > overbought              OR   close < SMA(fast_ma)
    """
    closes   = [c["close"] for c in candles]
    rsi      = calc_rsi(closes, rsi_period)
    sma_fast = calc_sma(closes, fast_ma)
    sma_slow = calc_sma(closes, slow_ma)
    trades, position = [], None
    for i in range(1, len(candles)):
        if rsi[i] is None or sma_fast[i] is None or sma_slow[i] is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        in_uptrend  = sma_fast[i] > sma_slow[i]
        if position is None and in_uptrend and rsi[i] < oversold:
            position = {"entry_date": date, "entry_price": price, "strategy": "rsi_pullback"}
        elif position is not None and (rsi[i] > overbought or price < sma_fast[i]):
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_keltner_breakout(candles, ema_period=20, atr_period=14, multiplier=2.0, **_):
    """ATR-normalized breakout (volatility-aware Donchian alternative).

    Upper = EMA(20) + multiplier · ATR(14)
    Entry: close > upper
    Exit:  close < EMA(20)
    """
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]
    ema    = calc_ema(closes, ema_period)
    atr    = calc_atr(highs, lows, closes, atr_period)
    trades, position = [], None
    for i in range(1, len(candles)):
        if ema[i] is None or atr[i] is None:
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        upper       = ema[i] + multiplier * atr[i]
        if position is None and price > upper:
            position = {"entry_date": date, "entry_price": price, "strategy": "keltner_breakout"}
        elif position is not None and price < ema[i]:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


def _run_triple_ema(candles, fast_period=20, slow_period=50, trend_period=200, **_):
    """EMA 20/50 cross gated by long-term trend filter.

    Entry: EMA(20) crosses ABOVE EMA(50)  AND  close > SMA(200)
    Exit:  EMA(20) crosses BELOW EMA(50)
    """
    closes    = [c["close"] for c in candles]
    ema_fast  = calc_ema(closes, fast_period)
    ema_slow  = calc_ema(closes, slow_period)
    sma_trend = calc_sma(closes, trend_period)
    trades, position = [], None
    for i in range(1, len(candles)):
        f, s, fp, sp, t = ema_fast[i], ema_slow[i], ema_fast[i-1], ema_slow[i-1], sma_trend[i]
        if None in (f, s, fp, sp, t):
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        bull_cross  = fp < sp and f >= s
        bear_cross  = fp > sp and f <= s
        if position is None and bull_cross and price > t:
            position = {"entry_date": date, "entry_price": price, "strategy": "triple_ema"}
        elif position is not None and bear_cross:
            trades.append({**position, "exit_date": date, "exit_price": price})
            position = None
    return trades


_STRATEGY_MAP = {
    "rsi":              _run_rsi,
    "bollinger":        _run_bollinger,
    "macd":             _run_macd,
    "ema_cross":        _run_ema_cross,
    "supertrend":       _run_supertrend,
    "donchian":         _run_donchian,
    "rsi_pullback":     _run_rsi_pullback,
    "keltner_breakout": _run_keltner_breakout,
    "triple_ema":       _run_triple_ema,
}


# ─── CIA-Specific Strategies (IDX) ───────────────────────────────────────────

_CIA_STRATEGY_LABELS = {
    "cia_superketat":   "CIA Superketat (close > MA5/10/20 semua ≤5%) — entry terbaik",
    "cia_ketat":        "CIA Ketat (close > MA5/10/20, salah satu ≤5%) — konfirmasi tren",
    "cia_kamehameha":   "CIA Kamehameha (volume > 2.5× V60, close > MA20) — ledakan volume",
    "cia_rainbow":      "CIA Rainbow (close > MA5/10/20/50/100/200) — no resistance",
    "cia_star":         "CIA Star (Ketat + Kamehameha bersamaan) — setup premium",
    "cia_sunflower":    "CIA Sunflower (Ketat pertama setelah gap up) — breakout gap",
}


def _calc_v60(volumes: list, period: int = 60) -> list:
    """Simple moving average of volume (V60 baseline for Kamehameha)."""
    result = [None] * len(volumes)
    for i in range(period - 1, len(volumes)):
        total = sum(volumes[i - period + 1 : i + 1])
        result[i] = total / period if total > 0 else None
    return result


def _pct_above(close: float, ma) -> float:
    """Percentage distance of close above MA. Returns inf if MA is None/0."""
    if ma is None or ma == 0:
        return float("inf")
    return (close - ma) / ma * 100


def _is_above(close: float, ma) -> bool:
    return ma is not None and close > ma


def _gap_up(candles: list, i: int) -> bool:
    """True if bar i opens above bar i-1's high (gap up)."""
    if i < 1:
        return False
    return candles[i]["low"] > candles[i - 1]["high"]


def _run_cia_superketat(candles, tight_pct=5.0, ara_guard=True, **_):
    """Entry: close > MA5/MA10/MA20 AND all distances ≤ tight_pct%.
    Exit: close < MA5 (CL) or position open at end."""
    closes = [c["close"] for c in candles]
    ma5    = calc_sma(closes, 5)
    ma10   = calc_sma(closes, 10)
    ma20   = calc_sma(closes, 20)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma20[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        d5  = _pct_above(price, ma5[i])
        d10 = _pct_above(price, ma10[i])
        d20 = _pct_above(price, ma20[i])
        in_ara = (ara_guard and prev_close is not None and
                  candles[i]["high"] >= prev_close * 1.20)
        entry_ok = (d5 >= 0 and d10 >= 0 and d20 >= 0 and
                    d5 <= tight_pct and d10 <= tight_pct and d20 <= tight_pct and
                    not in_ara)
        exit_ok  = position is not None and ma5[i] is not None and price < ma5[i]
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_superketat",
                        "setup_note": f"MA5:{d5:.1f}% MA10:{d10:.1f}% MA20:{d20:.1f}%"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA5"})
            position = None
        prev_close = price
    return trades


def _run_cia_ketat(candles, tight_pct=5.0, ara_guard=True, **_):
    """Entry: close > MA5/MA10/MA20 AND at least one distance ≤ tight_pct%.
    Exit: close < MA5 (CL)."""
    closes = [c["close"] for c in candles]
    ma5    = calc_sma(closes, 5)
    ma10   = calc_sma(closes, 10)
    ma20   = calc_sma(closes, 20)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma20[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        d5  = _pct_above(price, ma5[i])
        d10 = _pct_above(price, ma10[i])
        d20 = _pct_above(price, ma20[i])
        above_all = d5 >= 0 and d10 >= 0 and d20 >= 0
        any_tight = min(d5, d10, d20) <= tight_pct
        in_ara = (ara_guard and prev_close is not None and
                  candles[i]["high"] >= prev_close * 1.20)
        entry_ok = above_all and any_tight and not in_ara
        exit_ok  = position is not None and ma5[i] is not None and price < ma5[i]
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_ketat",
                        "setup_note": f"MA5:{d5:.1f}% MA10:{d10:.1f}% MA20:{d20:.1f}%"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA5"})
            position = None
        prev_close = price
    return trades


def _run_cia_kamehameha(candles, kamehameha_ratio=2.5, ara_guard=True, **_):
    """Entry: volume > kamehameha_ratio × V60 AND close > MA20.
    Exit: close < MA10 (CL) — allow more room since it's a vol spike play."""
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]
    ma10    = calc_sma(closes, 10)
    ma20    = calc_sma(closes, 20)
    v60     = _calc_v60(volumes, 60)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma20[i] is None or v60[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date  = candles[i]["close"], candles[i]["date"]
        vol          = candles[i]["volume"]
        is_kame      = v60[i] > 0 and vol >= kamehameha_ratio * v60[i]
        above_ma20   = price > ma20[i]
        in_ara = (ara_guard and prev_close is not None and
                  candles[i]["high"] >= prev_close * 1.20)
        entry_ok = is_kame and above_ma20 and not in_ara
        exit_ok  = position is not None and ma10[i] is not None and price < ma10[i]
        vol_ratio = round(vol / v60[i], 2) if v60[i] else 0
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_kamehameha",
                        "setup_note": f"Vol {vol_ratio}× V60"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA10"})
            position = None
        prev_close = price
    return trades


def _run_cia_rainbow(candles, ara_guard=True, **_):
    """Entry: close above ALL 6 MAs (5/10/20/50/100/200).
    Exit: close < MA20 (CL) — wide stop since long-term strength required."""
    closes = [c["close"] for c in candles]
    ma5    = calc_sma(closes, 5)
    ma10   = calc_sma(closes, 10)
    ma20   = calc_sma(closes, 20)
    ma50   = calc_sma(closes, 50)
    ma100  = calc_sma(closes, 100)
    ma200  = calc_sma(closes, 200)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma200[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        in_ara = (ara_guard and prev_close is not None and
                  candles[i]["high"] >= prev_close * 1.20)
        above_all = all(_is_above(price, m[i]) for m in (ma5, ma10, ma20, ma50, ma100, ma200))
        entry_ok  = above_all and not in_ara
        exit_ok   = position is not None and ma20[i] is not None and price < ma20[i]
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_rainbow",
                        "setup_note": "Above MA5/10/20/50/100/200"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA20"})
            position = None
        prev_close = price
    return trades


def _run_cia_star(candles, tight_pct=5.0, kamehameha_ratio=2.5, ara_guard=True, **_):
    """Entry: KETAT condition AND KAMEHAMEHA condition simultaneously.
    Exit: close < MA5 (CL) — tightest stop, premium setup."""
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]
    ma5     = calc_sma(closes, 5)
    ma10    = calc_sma(closes, 10)
    ma20    = calc_sma(closes, 20)
    v60     = _calc_v60(volumes, 60)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma20[i] is None or v60[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        vol  = candles[i]["volume"]
        d5   = _pct_above(price, ma5[i])
        d10  = _pct_above(price, ma10[i])
        d20  = _pct_above(price, ma20[i])
        ketat_ok = (d5 >= 0 and d10 >= 0 and d20 >= 0 and min(d5, d10, d20) <= tight_pct)
        kame_ok  = v60[i] > 0 and vol >= kamehameha_ratio * v60[i]
        in_ara   = (ara_guard and prev_close is not None and
                    candles[i]["high"] >= prev_close * 1.20)
        entry_ok = ketat_ok and kame_ok and not in_ara
        exit_ok  = position is not None and ma5[i] is not None and price < ma5[i]
        vol_ratio = round(vol / v60[i], 2) if v60[i] else 0
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_star",
                        "setup_note": f"Ketat MA5:{d5:.1f}% + Kame {vol_ratio}×V60"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA5"})
            position = None
        prev_close = price
    return trades


def _run_cia_sunflower(candles, tight_pct=5.0, ara_guard=True, **_):
    """Entry: first KETAT bar immediately after a gap up (low[i] > high[i-1]).
    Exit: close < MA5 (CL)."""
    closes = [c["close"] for c in candles]
    ma5    = calc_sma(closes, 5)
    ma10   = calc_sma(closes, 10)
    ma20   = calc_sma(closes, 20)
    trades, position = [], None
    prev_close = None
    for i in range(1, len(candles)):
        if ma20[i] is None:
            prev_close = candles[i]["close"]
            continue
        price, date = candles[i]["close"], candles[i]["date"]
        d5   = _pct_above(price, ma5[i])
        d10  = _pct_above(price, ma10[i])
        d20  = _pct_above(price, ma20[i])
        ketat_ok  = (d5 >= 0 and d10 >= 0 and d20 >= 0 and min(d5, d10, d20) <= tight_pct)
        gap_ok    = _gap_up(candles, i)
        in_ara    = (ara_guard and prev_close is not None and
                     candles[i]["high"] >= prev_close * 1.20)
        entry_ok  = ketat_ok and gap_ok and not in_ara
        exit_ok   = position is not None and ma5[i] is not None and price < ma5[i]
        if position is None and entry_ok:
            position = {"entry_date": date, "entry_price": price,
                        "strategy": "cia_sunflower",
                        "setup_note": f"Gap up + Ketat MA5:{d5:.1f}%"}
        elif exit_ok:
            trades.append({**position, "exit_date": date, "exit_price": price,
                           "exit_reason": "CL: close < MA5"})
            position = None
        prev_close = price
    return trades


_CIA_STRATEGY_MAP = {
    "cia_superketat":  _run_cia_superketat,
    "cia_ketat":       _run_cia_ketat,
    "cia_kamehameha":  _run_cia_kamehameha,
    "cia_rainbow":     _run_cia_rainbow,
    "cia_star":        _run_cia_star,
    "cia_sunflower":   _run_cia_sunflower,
}

# IDX default commission: 0.15% buy + 0.25% sell (typical broker Indonesia)
_IDX_COMMISSION_BUY  = 0.15
_IDX_COMMISSION_SELL = 0.25


def _apply_idx_costs(trades: list, commission_buy_pct: float,
                     commission_sell_pct: float, slippage_pct: float) -> list:
    """Apply separate buy/sell commission (IDX structure) + slippage."""
    result = []
    for t in trades:
        gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        cost  = commission_buy_pct + commission_sell_pct + slippage_pct * 2
        net   = round(gross - cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3),
                        "cost_pct": round(-cost, 3)})
    return result


def _apply_arb_guard(trades: list, candles: list,
                     ara_limit: float = 0.20, arb_limit: float = 0.20) -> list:
    """Post-process trades: force exit if ARB (-arb_limit) is hit during holding.

    Also flags trades where entry occurred near ARA (potential liquidity risk).
    ARB = Auto Rejection Below (IDX price floor per session).
    ARA = Auto Rejection Above (IDX price ceiling per session).
    """
    date_to_candle = {c["date"]: c for c in candles}
    candle_dates   = [c["date"] for c in candles]
    date_index     = {d: i for i, d in enumerate(candle_dates)}

    result = []
    for t in trades:
        entry_i = date_index.get(t["entry_date"])
        exit_i  = date_index.get(t["exit_date"])
        if entry_i is None or exit_i is None:
            result.append({**t, "ara_arb_flag": "unknown"})
            continue

        arb_hit    = False
        arb_date   = None
        arb_price  = None
        ara_entry  = False

        # Check ARA at entry (entry candle high ≥ prev_close * 1.20)
        if entry_i > 0:
            prev_c = candles[entry_i - 1]["close"]
            if candles[entry_i]["high"] >= prev_c * (1 + ara_limit * 0.9):
                ara_entry = True

        # Scan holding period for ARB
        for j in range(entry_i + 1, min(exit_i + 1, len(candles))):
            prev_close_j = candles[j - 1]["close"]
            low_j        = candles[j]["low"]
            arb_floor    = prev_close_j * (1 - arb_limit)
            if low_j <= arb_floor:
                arb_hit   = True
                arb_date  = candles[j]["date"]
                arb_price = round(arb_floor, 4)
                break

        flag = []
        if ara_entry:
            flag.append("ARA_ENTRY_RISK")
        if arb_hit:
            flag.append("ARB_TRIGGERED")

        extra = {"ara_arb_flag": ", ".join(flag) if flag else "clean"}
        if arb_hit:
            # Override exit to ARB level
            arb_return = round(
                (arb_price - t["entry_price"]) / t["entry_price"] * 100
                + t.get("cost_pct", 0), 3)
            extra.update({
                "exit_date":   arb_date,
                "exit_price":  arb_price,
                "return_pct":  arb_return,
                "exit_reason": f"ARB triggered at {arb_price}",
            })

        result.append({**t, **extra})
    return result


def _build_cia_summary(trades: list, candles: list) -> dict:
    """Additional CIA-specific trade summary."""
    if not trades:
        return {}
    ara_risk  = sum(1 for t in trades if "ARA_ENTRY_RISK"   in str(t.get("ara_arb_flag", "")))
    arb_hits  = sum(1 for t in trades if "ARB_TRIGGERED"    in str(t.get("ara_arb_flag", "")))
    clean     = sum(1 for t in trades if t.get("ara_arb_flag") == "clean")
    avg_hold  = None
    hold_days = []
    for t in trades:
        try:
            e = datetime.fromisoformat(t["entry_date"])
            x = datetime.fromisoformat(t["exit_date"])
            hold_days.append(max(1, (x - e).days))
        except Exception:
            pass
    if hold_days:
        avg_hold = round(sum(hold_days) / len(hold_days), 1)
    return {
        "clean_trades":         clean,
        "ara_entry_risk_count": ara_risk,
        "arb_stopped_count":    arb_hits,
        "avg_hold_days":        avg_hold,
    }


# ─── Transaction Costs ────────────────────────────────────────────────────────

def _apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    total_cost_pct = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net   = round(gross - total_cost_pct, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3),
                        "cost_pct": round(-total_cost_pct, 3)})
    return result


# ─── Trade Log & Equity Curve ─────────────────────────────────────────────────

def _build_trade_log(trades: list[dict], initial_capital: float) -> list[dict]:
    """Full per-trade log with holding days, running capital, cumulative return."""
    capital = initial_capital
    log = []
    for i, t in enumerate(trades):
        capital_before = capital
        capital *= (1 + t["return_pct"] / 100)
        cum_return = round((capital - initial_capital) / initial_capital * 100, 2)
        try:
            entry_dt     = datetime.fromisoformat(t["entry_date"].replace(" ", "T"))
            exit_dt      = datetime.fromisoformat(t["exit_date"].replace(" ", "T"))
            holding_days = max(1, (exit_dt - entry_dt).days)
        except Exception:
            holding_days = None
        log.append({
            "trade_no":              i + 1,
            "entry_date":            t["entry_date"],
            "entry_price":           t["entry_price"],
            "exit_date":             t["exit_date"],
            "exit_price":            t["exit_price"],
            "holding_days":          holding_days,
            "return_pct":            t["return_pct"],
            "gross_return_pct":      t.get("gross_return_pct", t["return_pct"]),
            "cost_pct":              t.get("cost_pct", 0),
            "capital_before":        round(capital_before, 2),
            "capital_after":         round(capital, 2),
            "cumulative_return_pct": cum_return,
        })
    return log


def _build_equity_curve(trades: list[dict], initial_capital: float) -> list[dict]:
    """Equity curve: capital + drawdown at each trade exit."""
    capital = initial_capital
    peak    = capital
    curve   = [{"date": "start", "equity": round(capital, 2), "drawdown_pct": 0.0}]
    for t in trades:
        capital *= (1 + t["return_pct"] / 100)
        peak     = max(peak, capital)
        dd       = round((peak - capital) / peak * 100, 2)
        curve.append({
            "date":         t["exit_date"],
            "equity":       round(capital, 2),
            "drawdown_pct": -dd,
        })
    return curve


# ─── Metrics ──────────────────────────────────────────────────────────────────

def _calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1d") -> dict:
    empty = {
        "total_trades": 0, "win_rate_pct": 0, "winning_trades": 0, "losing_trades": 0,
        "total_return_pct": 0, "final_capital": initial_capital,
        "avg_gain_pct": 0, "avg_loss_pct": 0, "max_drawdown_pct": 0,
        "profit_factor": 0, "sharpe_ratio": 0, "calmar_ratio": 0,
        "expectancy_pct": 0, "best_trade": None, "worst_trade": None,
    }
    if not trades:
        return empty

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = initial_capital
    peak    = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak   = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    total_return  = (capital - initial_capital) / initial_capital * 100
    avg_gain      = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss      = sum(t["return_pct"] for t in losers)  / len(losers)  if losers  else 0
    gp            = sum(t["return_pct"] for t in winners)
    gl            = abs(sum(t["return_pct"] for t in losers))
    profit_factor = round(gp / gl, 2) if gl > 0 else float("inf")

    ann  = _ANNUALIZATION.get(interval, 252)
    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    calmar = round(total_return / max_dd, 2) if max_dd > 0 else 0.0

    wr         = len(winners) / len(trades)
    expectancy = round(wr * avg_gain + (1 - wr) * avg_loss, 2)
    best       = max(trades, key=lambda t: t["return_pct"])
    worst      = min(trades, key=lambda t: t["return_pct"])

    return {
        "total_trades":     len(trades),
        "winning_trades":   len(winners),
        "losing_trades":    len(losers),
        "win_rate_pct":     round(wr * 100, 1),
        "final_capital":    round(capital, 2),
        "total_return_pct": round(total_return, 2),
        "avg_gain_pct":     round(avg_gain, 2),
        "avg_loss_pct":     round(avg_loss, 2),
        "max_drawdown_pct": round(-max_dd, 2),
        "profit_factor":    profit_factor,
        "sharpe_ratio":     sharpe,
        "calmar_ratio":     calmar,
        "expectancy_pct":   expectancy,
        "best_trade":       {k: best[k]  for k in ("entry_date", "exit_date", "return_pct")},
        "worst_trade":      {k: worst[k] for k in ("entry_date", "exit_date", "return_pct")},
    }


def _buy_and_hold_return(candles: list[dict]) -> float:
    if len(candles) < 2:
        return 0.0
    return round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)


# ─── Public API: run_backtest ─────────────────────────────────────────────────

def run_backtest(
    symbol: str,
    strategy: str,
    period: str = "1y",
    initial_capital: float = 10_000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    interval: str = "1d",
    include_trade_log: bool = False,
    include_equity_curve: bool = False,
) -> dict:
    strategy = strategy.lower().strip()
    period   = period.lower().strip()
    interval = interval.lower().strip()

    if strategy not in _STRATEGY_MAP:
        return {"error": f"Unknown strategy '{strategy}'. Choose: {', '.join(_STRATEGY_MAP)}"}
    if period not in _VALID_PERIODS:
        return {"error": f"Invalid period '{period}'. Choose: {', '.join(_VALID_PERIODS)}"}
    if interval not in _VALID_INTERVALS:
        return {"error": f"Invalid interval '{interval}'. Choose: 1d or 1h"}

    try:
        candles = _fetch_ohlcv(symbol, period, interval)
    except Exception as e:
        return {"error": f"Failed to fetch data for '{symbol}': {e}"}

    min_bars = 30 if interval == "1d" else 100
    if len(candles) < min_bars:
        return {"error": f"Not enough data ({len(candles)} bars). Try a longer period."}

    if strategy in _SMA200_STRATEGIES and len(candles) < _SMA200_MIN_BARS:
        return {"error": (f"Strategy '{strategy}' needs ≥{_SMA200_MIN_BARS} bars "
                          f"(SMA200 warmup); got {len(candles)}. "
                          f"Use period='1y' or '2y'.")}

    raw_trades = _STRATEGY_MAP[strategy](candles)
    trades     = _apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics    = _calc_metrics(trades, initial_capital, interval)
    bnh        = _buy_and_hold_return(candles)

    result = {
        "symbol":                  symbol.upper(),
        "strategy":                strategy,
        "strategy_label":          _STRATEGY_LABELS[strategy],
        "period":                  period,
        "interval":                interval,
        "timeframe":               "Hourly (1h)" if interval == "1h" else "Daily (1d)",
        "candles_analyzed":        len(candles),
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "initial_capital":         round(initial_capital, 2),
        "commission_pct":          commission_pct,
        "slippage_pct":            slippage_pct,
        **metrics,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct":     round(metrics["total_return_pct"] - bnh, 2),
        "recent_trades":           trades[-5:],
        "data_source":             "Yahoo Finance",
        "disclaimer":              "Past performance does not guarantee future results. For educational use only.",
        "timestamp":               datetime.now(timezone.utc).isoformat(),
    }

    if include_trade_log:
        result["trade_log"] = _build_trade_log(trades, initial_capital)

    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades, initial_capital)

    return result


# ─── Public API: run_cia_backtest ─────────────────────────────────────────────

def run_cia_backtest(
    symbol: str,
    strategy: str,
    period: str = "1y",
    initial_capital: float = 10_000_000.0,
    commission_buy_pct: float = _IDX_COMMISSION_BUY,
    commission_sell_pct: float = _IDX_COMMISSION_SELL,
    slippage_pct: float = 0.05,
    tight_pct: float = 5.0,
    kamehameha_ratio: float = 2.5,
    ara_guard: bool = True,
    ara_arb_simulation: bool = True,
    include_trade_log: bool = False,
    include_equity_curve: bool = False,
) -> dict:
    """Run CIA-style IDX backtest for one symbol.

    CIA strategies simulate real IDX trading rules:
      - ARA guard: skip entry if candle is already at +20% auto-rejection
      - ARB simulation: force exit if price hits -20% floor during holding
      - IDX broker commission: buy (0.15%) + sell (0.25%) separate

    Args:
        symbol:              IDX ticker, e.g. "BBCA" (auto-appends .JK)
        strategy:            cia_superketat | cia_ketat | cia_kamehameha |
                             cia_rainbow | cia_star | cia_sunflower
        period:              1mo | 3mo | 6mo | 1y | 2y
        initial_capital:     Starting capital in IDR (default 10 juta)
        commission_buy_pct:  Buy-side broker fee % (default 0.15%)
        commission_sell_pct: Sell-side broker fee % (default 0.25%)
        slippage_pct:        Slippage per side % (default 0.05%)
        tight_pct:           Max % distance to MA for "ketat" condition (default 5%)
        kamehameha_ratio:    Min volume multiplier vs V60 (default 2.5×)
        ara_guard:           Skip entry on ARA day (default True)
        ara_arb_simulation:  Force exit at ARB floor if hit (default True)
        include_trade_log:   Include full per-trade log
        include_equity_curve: Include equity curve data
    """
    strategy = strategy.lower().strip()
    period   = period.lower().strip()

    if strategy not in _CIA_STRATEGY_MAP:
        return {"error": (f"Unknown CIA strategy '{strategy}'. "
                          f"Choose: {', '.join(_CIA_STRATEGY_MAP)}")}
    if period not in _VALID_PERIODS:
        return {"error": f"Invalid period '{period}'. Choose: {', '.join(_VALID_PERIODS)}"}

    yf_symbol = symbol.upper().strip()
    if not yf_symbol.endswith(".JK"):
        yf_symbol = yf_symbol + ".JK"

    try:
        candles = _fetch_ohlcv(yf_symbol, period, "1d")
    except Exception as e:
        return {"error": f"Failed to fetch data for '{yf_symbol}': {e}"}

    min_bars = 70 if strategy == "cia_rainbow" else 30
    if strategy in ("cia_kamehameha", "cia_star"):
        min_bars = 65
    if len(candles) < min_bars:
        return {"error": (f"Not enough data ({len(candles)} bars). "
                          f"Need ≥{min_bars} bars. Use a longer period.")}

    fn_kwargs = {
        "tight_pct":        tight_pct,
        "kamehameha_ratio": kamehameha_ratio,
        "ara_guard":        ara_guard,
    }
    raw_trades = _CIA_STRATEGY_MAP[strategy](candles, **fn_kwargs)
    trades     = _apply_idx_costs(raw_trades, commission_buy_pct,
                                   commission_sell_pct, slippage_pct)

    if ara_arb_simulation:
        trades = _apply_arb_guard(trades, candles)

    metrics    = _calc_metrics(trades, initial_capital)
    bnh        = _buy_and_hold_return(candles)
    cia_extra  = _build_cia_summary(trades, candles)

    result = {
        "symbol":                  symbol.upper(),
        "yf_symbol":               yf_symbol,
        "strategy":                strategy,
        "strategy_label":          _CIA_STRATEGY_LABELS[strategy],
        "period":                  period,
        "candles_analyzed":        len(candles),
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "initial_capital_idr":     round(initial_capital, 0),
        "commission_buy_pct":      commission_buy_pct,
        "commission_sell_pct":     commission_sell_pct,
        "slippage_pct":            slippage_pct,
        "tight_pct":               tight_pct,
        "kamehameha_ratio":        kamehameha_ratio,
        "ara_guard_enabled":       ara_guard,
        "arb_simulation_enabled":  ara_arb_simulation,
        **metrics,
        **cia_extra,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct":     round(metrics["total_return_pct"] - bnh, 2),
        "recent_trades":           trades[-5:],
        "data_source":             "Yahoo Finance (.JK)",
        "disclaimer":              "Past performance does not guarantee future results. For educational use only.",
        "timestamp":               datetime.now(timezone.utc).isoformat(),
    }

    if include_trade_log:
        result["trade_log"] = _build_trade_log(trades, initial_capital)
    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades, initial_capital)

    return result


# ─── Public API: compare_cia_strategies ──────────────────────────────────────

def compare_cia_strategies(
    symbol: str,
    period: str = "1y",
    initial_capital: float = 10_000_000.0,
    commission_buy_pct: float = _IDX_COMMISSION_BUY,
    commission_sell_pct: float = _IDX_COMMISSION_SELL,
    slippage_pct: float = 0.05,
    tight_pct: float = 5.0,
    kamehameha_ratio: float = 2.5,
    ara_guard: bool = True,
    ara_arb_simulation: bool = True,
) -> dict:
    """Run all 6 CIA strategies on one IDX symbol and rank by performance."""
    period = period.lower().strip()
    if period not in _VALID_PERIODS:
        return {"error": f"Invalid period '{period}'. Choose: {', '.join(_VALID_PERIODS)}"}

    yf_symbol = symbol.upper().strip()
    if not yf_symbol.endswith(".JK"):
        yf_symbol = yf_symbol + ".JK"

    try:
        candles = _fetch_ohlcv(yf_symbol, period, "1d")
    except Exception as e:
        return {"error": f"Failed to fetch data for '{yf_symbol}': {e}"}

    if len(candles) < 65:
        return {"error": f"Not enough data ({len(candles)} bars). Need ≥65 bars."}

    fn_kwargs = {
        "tight_pct":        tight_pct,
        "kamehameha_ratio": kamehameha_ratio,
        "ara_guard":        ara_guard,
    }

    ranking = []
    for strat, fn in _CIA_STRATEGY_MAP.items():
        raw    = fn(candles, **fn_kwargs)
        trades = _apply_idx_costs(raw, commission_buy_pct, commission_sell_pct, slippage_pct)
        if ara_arb_simulation:
            trades = _apply_arb_guard(trades, candles)
        m      = _calc_metrics(trades, initial_capital)
        cia_x  = _build_cia_summary(trades, candles)
        ranking.append({
            "strategy":           strat,
            "strategy_label":     _CIA_STRATEGY_LABELS[strat],
            "total_return_pct":   m["total_return_pct"],
            "win_rate_pct":       m["win_rate_pct"],
            "total_trades":       m["total_trades"],
            "profit_factor":      m["profit_factor"],
            "sharpe_ratio":       m["sharpe_ratio"],
            "max_drawdown_pct":   m["max_drawdown_pct"],
            "avg_hold_days":      cia_x.get("avg_hold_days"),
            "arb_stopped_count":  cia_x.get("arb_stopped_count", 0),
            "clean_trades":       cia_x.get("clean_trades", 0),
        })

    ranking.sort(key=lambda x: x["total_return_pct"], reverse=True)
    for i, r in enumerate(ranking):
        r["rank"] = i + 1

    bnh = _buy_and_hold_return(candles)

    return {
        "symbol":                  symbol.upper(),
        "yf_symbol":               yf_symbol,
        "period":                  period,
        "candles_analyzed":        len(candles),
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "initial_capital_idr":     round(initial_capital, 0),
        "buy_and_hold_return_pct": bnh,
        "best_cia_strategy":       ranking[0]["strategy"] if ranking else None,
        "ranking":                 ranking,
        "parameters": {
            "tight_pct":        tight_pct,
            "kamehameha_ratio": kamehameha_ratio,
            "ara_guard":        ara_guard,
            "arb_simulation":   ara_arb_simulation,
            "commission_buy":   commission_buy_pct,
            "commission_sell":  commission_sell_pct,
        },
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


# ─── Public API: compare_strategies ──────────────────────────────────────────

def compare_strategies(
    symbol: str,
    period: str = "1y",
    initial_capital: float = 10_000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    interval: str = "1d",
) -> dict:
    """Run all 6 strategies on one symbol. Supports 1d and 1h intervals."""
    interval = interval.lower().strip()
    if interval not in _VALID_INTERVALS:
        return {"error": f"Invalid interval '{interval}'. Choose: 1d or 1h"}

    try:
        candles = _fetch_ohlcv(symbol, period, interval)
    except Exception as e:
        return {"error": f"Failed to fetch data for '{symbol}': {e}"}

    min_bars = 30 if interval == "1d" else 100
    if len(candles) < min_bars:
        return {"error": f"Not enough data ({len(candles)} bars)."}

    sma200_ok = len(candles) >= _SMA200_MIN_BARS

    results = []
    for strat, fn in _STRATEGY_MAP.items():
        raw    = fn(candles)
        trades = _apply_costs(raw, commission_pct, slippage_pct)
        m      = _calc_metrics(trades, initial_capital, interval)
        results.append({
            "strategy":         strat,
            "strategy_label":   _STRATEGY_LABELS[strat],
            "total_return_pct": m["total_return_pct"],
            "win_rate_pct":     m["win_rate_pct"],
            "total_trades":     m["total_trades"],
            "profit_factor":    m["profit_factor"],
            "sharpe_ratio":     m["sharpe_ratio"],
            "calmar_ratio":     m["calmar_ratio"],
            "max_drawdown_pct": m["max_drawdown_pct"],
            "expectancy_pct":   m["expectancy_pct"],
        })

    results.sort(key=lambda x: x["total_return_pct"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    bnh = _buy_and_hold_return(candles)

    warnings = None
    if not sma200_ok:
        warnings = (f"Strategies {sorted(_SMA200_STRATEGIES)} need ≥{_SMA200_MIN_BARS} "
                    f"bars (use period='1y' or '2y') to produce signals; "
                    f"their zero-trade results below are not meaningful.")

    return {
        "symbol":                  symbol.upper(),
        "period":                  period,
        "interval":                interval,
        "timeframe":               "Hourly (1h)" if interval == "1h" else "Daily (1d)",
        "candles_analyzed":        len(candles),
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "initial_capital":         round(initial_capital, 2),
        "commission_pct":          commission_pct,
        "slippage_pct":            slippage_pct,
        "buy_and_hold_return_pct": bnh,
        "winner":                  results[0]["strategy"] if results else None,
        "ranking":                 results,
        "warnings":                warnings,
        "disclaimer":              "Past performance does not guarantee future results.",
        "timestamp":               datetime.now(timezone.utc).isoformat(),
    }


# ─── Public API: walk_forward_backtest ────────────────────────────────────────

def walk_forward_backtest(
    symbol: str,
    strategy: str,
    period: str = "2y",
    initial_capital: float = 10_000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    n_splits: int = 3,
    train_ratio: float = 0.7,
    interval: str = "1d",
) -> dict:
    """
    Walk-forward backtesting — detect overfitting via train/test splits.

    Splits full history into n_splits folds. Each fold:
      - Train (70%): in-sample strategy simulation
      - Test  (30%): out-of-sample forward validation

    Robustness score (test_return / train_return):
      >= 0.8  → ROBUST    (no overfitting)
      >= 0.5  → MODERATE  (some degradation)
      >= 0.2  → WEAK      (likely overfitted)
      < 0.2   → OVERFITTED (do not trade live)
    """
    strategy = strategy.lower().strip()
    period   = period.lower().strip()
    interval = interval.lower().strip()

    if strategy not in _STRATEGY_MAP:
        return {"error": f"Unknown strategy '{strategy}'. Choose: {', '.join(_STRATEGY_MAP)}"}
    if period not in _VALID_PERIODS:
        return {"error": f"Invalid period '{period}'. Choose: {', '.join(_VALID_PERIODS)}"}
    if interval not in _VALID_INTERVALS:
        return {"error": f"Invalid interval '{interval}'. Choose: 1d or 1h"}
    if not (2 <= n_splits <= 10):
        return {"error": "n_splits must be between 2 and 10"}
    if not (0.5 <= train_ratio <= 0.9):
        return {"error": "train_ratio must be between 0.5 and 0.9"}
    if strategy in _SMA200_STRATEGIES:
        return {"error": (f"Strategy '{strategy}' requires SMA200 warmup "
                          f"(~{_SMA200_MIN_BARS} bars) which exceeds typical "
                          f"walk-forward fold sizes. Use run_backtest with "
                          f"period='2y' instead, or pick a shorter-warmup strategy.")}

    try:
        candles = _fetch_ohlcv(symbol, period, interval)
    except Exception as e:
        return {"error": f"Failed to fetch data for '{symbol}': {e}"}

    min_bars = max(60, n_splits * 20)
    if len(candles) < min_bars:
        return {"error": f"Not enough data ({len(candles)} bars) for {n_splits} splits. Try longer period."}

    fn        = _STRATEGY_MAP[strategy]
    fold_size = len(candles) // n_splits

    folds: list[dict]   = []
    all_test_trades: list[dict] = []

    for fold_i in range(n_splits):
        start  = fold_i * fold_size
        end    = (start + fold_size) if fold_i < n_splits - 1 else len(candles)
        window = candles[start:end]
        split  = int(len(window) * train_ratio)

        train_c = window[:split]
        test_c  = window[split:]

        if len(train_c) < 20 or len(test_c) < 5:
            continue

        train_t = _apply_costs(fn(train_c), commission_pct, slippage_pct)
        test_t  = _apply_costs(fn(test_c),  commission_pct, slippage_pct)
        train_m = _calc_metrics(train_t, initial_capital, interval)
        test_m  = _calc_metrics(test_t,  initial_capital, interval)

        all_test_trades.extend(test_t)

        tr, te = train_m["total_return_pct"], test_m["total_return_pct"]
        if tr == 0:
            fold_rob = 1.0 if te == 0 else 0.0
        elif tr < 0 and te < 0:
            fold_rob = round(min(te / tr, 2.0), 2)
        elif tr < 0:
            fold_rob = 0.0
        else:
            fold_rob = round(max(min(te / tr, 2.0), -1.0), 2)

        folds.append({
            "fold":                  fold_i + 1,
            "train_from":            train_c[0]["date"],
            "train_to":              train_c[-1]["date"],
            "train_candles":         len(train_c),
            "train_return_pct":      train_m["total_return_pct"],
            "train_trades":          train_m["total_trades"],
            "train_sharpe":          train_m["sharpe_ratio"],
            "test_from":             test_c[0]["date"],
            "test_to":               test_c[-1]["date"],
            "test_candles":          len(test_c),
            "test_return_pct":       test_m["total_return_pct"],
            "test_trades":           test_m["total_trades"],
            "test_sharpe":           test_m["sharpe_ratio"],
            "fold_robustness_score": fold_rob,
        })

    if not folds:
        return {"error": "Could not generate any valid folds. Try a longer period or fewer splits."}

    avg_train  = round(statistics.mean(f["train_return_pct"] for f in folds), 2)
    avg_test   = round(statistics.mean(f["test_return_pct"]  for f in folds), 2)
    avg_robust = round(statistics.mean(f["fold_robustness_score"] for f in folds), 2)
    oos_m      = _calc_metrics(all_test_trades, initial_capital, interval)

    if avg_robust >= 0.8:
        verdict = "ROBUST — strategy performs consistently in-sample and out-of-sample"
    elif avg_robust >= 0.5:
        verdict = "MODERATE — some degradation out-of-sample, use with caution"
    elif avg_robust >= 0.2:
        verdict = "WEAK — significant out-of-sample degradation, likely overfitted"
    else:
        verdict = "OVERFITTED — strategy fails out-of-sample, do not trade live"

    return {
        "symbol":                  symbol.upper(),
        "strategy":                strategy,
        "strategy_label":          _STRATEGY_LABELS[strategy],
        "period":                  period,
        "interval":                interval,
        "timeframe":               "Hourly (1h)" if interval == "1h" else "Daily (1d)",
        "total_candles":           len(candles),
        "n_splits":                n_splits,
        "train_ratio":             train_ratio,
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "avg_train_return_pct":    avg_train,
        "avg_test_return_pct":     avg_test,
        "robustness_score":        avg_robust,
        "verdict":                 verdict,
        "oos_total_trades":        oos_m["total_trades"],
        "oos_win_rate_pct":        oos_m["win_rate_pct"],
        "oos_sharpe_ratio":        oos_m["sharpe_ratio"],
        "oos_max_drawdown_pct":    oos_m["max_drawdown_pct"],
        "oos_total_return_pct":    oos_m["total_return_pct"],
        "buy_and_hold_return_pct": _buy_and_hold_return(candles),
        "folds":                   folds,
        "initial_capital":         round(initial_capital, 2),
        "commission_pct":          commission_pct,
        "slippage_pct":            slippage_pct,
        "data_source":             "Yahoo Finance",
        "disclaimer":              "Past performance does not guarantee future results. For educational use only.",
        "timestamp":               datetime.now(timezone.utc).isoformat(),
    }
