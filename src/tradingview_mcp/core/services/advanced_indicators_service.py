"""
Advanced Technical Indicators Service — get_advanced_indicators_for_stock.

Mengambil indikator teknikal lanjutan dari dua sumber:
1. tradingview_ta  : ADX/DMI, CCI, Williams %R, StochRSI
2. yfinance + pandas_ta : Stochastic Slow (10,5,5), Ichimoku Cloud, Volume Profile

Dirancang sebagai standalone tool — tidak memodifikasi idx_decision_service.py.
"""
from __future__ import annotations

import re
from typing import Optional

# ── tradingview_ta (via resilience layer) ─────────────────────────────────────
try:
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as _get_multiple_analysis,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

_IDX_SCREENER = "indonesia"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_ticker(ticker: str) -> str:
    return re.sub(r"\.JK$", "", ticker.strip().upper())


def _safe_float(val) -> Optional[float]:
    """Convert to float, return None on failure."""
    import math
    try:
        # Handle pandas Series with a single element
        try:
            import pandas as _pd
            if isinstance(val, _pd.Series):
                val = val.iloc[0]
        except Exception:
            pass
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except Exception:
        return None


# ── ADX/DMI ──────────────────────────────────────────────────────────────────

def _build_adx_dmi(ind: dict) -> dict:
    adx       = _safe_float(ind.get("ADX"))
    plus_di   = _safe_float(ind.get("ADX+DI"))
    minus_di  = _safe_float(ind.get("ADX-DI"))
    prev_plus  = _safe_float(ind.get("ADX+DI[1]"))
    prev_minus = _safe_float(ind.get("ADX-DI[1]"))

    # Directional signal
    if plus_di is not None and minus_di is not None:
        if plus_di > minus_di:
            signal = "BULL"
        elif minus_di > plus_di:
            signal = "BEAR"
        else:
            signal = "NEUTRAL"
    else:
        signal = "NEUTRAL"

    # Trend strength
    if adx is not None:
        if adx > 25:
            strength = "STRONG"
        elif adx >= 20:
            strength = "MODERATE"
        else:
            strength = "WEAK"
    else:
        strength = "UNKNOWN"

    return {
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "prev_plus_di": prev_plus,
        "prev_minus_di": prev_minus,
        "signal": signal,
        "strength": strength,
    }


# ── CCI ──────────────────────────────────────────────────────────────────────

def _build_cci(ind: dict) -> dict:
    value = _safe_float(ind.get("CCI20"))
    prev  = _safe_float(ind.get("CCI20[1]"))

    if value is not None:
        if value > 100:
            signal = "OVERBOUGHT"
        elif value < -100:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"
    else:
        signal = "NEUTRAL"

    return {"value": value, "prev": prev, "signal": signal}


# ── Williams %R ──────────────────────────────────────────────────────────────

def _build_williams_r(ind: dict) -> dict:
    value = _safe_float(ind.get("W.R"))

    if value is not None:
        if value > -20:
            signal = "OVERBOUGHT"
        elif value < -80:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"
    else:
        signal = "NEUTRAL"

    return {"value": value, "signal": signal}


# ── StochRSI ─────────────────────────────────────────────────────────────────

def _build_stoch_rsi(ind: dict) -> dict:
    k = _safe_float(ind.get("Stoch.RSI.K"))

    if k is not None:
        if k > 80:
            signal = "OVERBOUGHT"
        elif k < 20:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"
    else:
        signal = "NEUTRAL"

    return {"k": k, "signal": signal}


# ── Stochastic Slow (10,5,5) via pandas_ta or pure pandas ────────────────────

def _stoch_slow_pure_pandas(df, k_period: int = 10, smooth_k: int = 5, d_period: int = 5):
    """
    Compute Stochastic Slow (k_period, smooth_k, d_period) using pure pandas.

    Formula:
      raw_k  = 100 * (close - lowest_low_k) / (highest_high_k - lowest_low_k)
      %K     = SMA(raw_k, smooth_k)   ← "slow K"
      %D     = SMA(%K, d_period)       ← signal line
    """
    import pandas as pd

    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    lowest_low   = low.rolling(k_period, min_periods=k_period).min()
    highest_high = high.rolling(k_period, min_periods=k_period).max()

    denom = highest_high - lowest_low
    raw_k = 100 * (close - lowest_low) / denom.replace(0, float("nan"))

    stoch_k = raw_k.rolling(smooth_k, min_periods=smooth_k).mean()
    stoch_d = stoch_k.rolling(d_period, min_periods=d_period).mean()

    return stoch_k, stoch_d


def _build_stoch_slow(df) -> dict:
    """Compute Stochastic Slow (10,5,5). Uses pandas_ta if available, else pure pandas."""
    try:
        # Try pandas_ta first
        try:
            import pandas_ta as ta  # type: ignore
            high  = df["High"]
            low   = df["Low"]
            close = df["Close"]
            stoch = ta.stoch(high, low, close, k=10, d=5, smooth_k=5)
            if stoch is not None and not stoch.empty:
                cols = list(stoch.columns)
                k_col = next((c for c in cols if c.startswith("STOCHk")), None)
                d_col = next((c for c in cols if c.startswith("STOCHd")), None)
                k_val = _safe_float(stoch[k_col].iloc[-1]) if k_col else None
                d_val = _safe_float(stoch[d_col].iloc[-1]) if d_col else None
                k_prev = _safe_float(stoch[k_col].iloc[-2]) if k_col and len(stoch) >= 2 else None
                d_prev = _safe_float(stoch[d_col].iloc[-2]) if d_col and len(stoch) >= 2 else None
                source = "pandas_ta"
            else:
                raise ValueError("Empty result from pandas_ta")
        except ImportError:
            # Fallback: pure pandas implementation
            stoch_k, stoch_d = _stoch_slow_pure_pandas(df, k_period=10, smooth_k=5, d_period=5)
            k_val  = _safe_float(stoch_k.iloc[-1])
            d_val  = _safe_float(stoch_d.iloc[-1])
            k_prev = _safe_float(stoch_k.iloc[-2]) if len(stoch_k) >= 2 else None
            d_prev = _safe_float(stoch_d.iloc[-2]) if len(stoch_d) >= 2 else None
            source = "pure_pandas"

        # Signal determination
        signal = "NEUTRAL"
        if k_val is not None:
            if k_val > 80:
                signal = "OVERBOUGHT"
            elif k_val < 20:
                signal = "OVERSOLD"
            # Bullish crossover check
            if (d_val is not None and k_prev is not None and d_prev is not None):
                if k_val > d_val and k_prev <= d_prev:
                    signal = "BULLISH_CROSS"

        return {"k": k_val, "d": d_val, "signal": signal, "_source": source}

    except Exception as e:
        return {"k": None, "d": None, "signal": "ERROR", "error": str(e)}


# ── Ichimoku via pandas_ta or pure pandas ─────────────────────────────────────

def _ichimoku_pure_pandas(df, tenkan_period: int = 9, kijun_period: int = 26,
                           senkou_b_period: int = 52):
    """
    Compute Ichimoku Cloud components using pure pandas.

    Tenkan-sen  = (highest_high_9  + lowest_low_9)  / 2
    Kijun-sen   = (highest_high_26 + lowest_low_26) / 2
    Senkou A    = (Tenkan + Kijun) / 2  (current bar, no displacement)
    Senkou B    = (highest_high_52 + lowest_low_52) / 2
    """
    high  = df["High"]
    low   = df["Low"]

    def _donchian_mid(period):
        return (high.rolling(period, min_periods=period).max() +
                low.rolling(period,  min_periods=period).min()) / 2

    tenkan = _donchian_mid(tenkan_period)
    kijun  = _donchian_mid(kijun_period)
    span_a = (tenkan + kijun) / 2
    span_b = _donchian_mid(senkou_b_period)

    return tenkan, kijun, span_a, span_b


def _build_ichimoku(df, ind: dict) -> dict:
    """Compute full Ichimoku. Uses pandas_ta if available, else pure pandas."""
    close = df["Close"]

    try:
        source = "pure_pandas"
        try:
            import pandas_ta as ta  # type: ignore
            high = df["High"]
            low  = df["Low"]
            ichi_result = ta.ichimoku(high, low, close, lookahead=False)
            ichi_df = ichi_result[0] if isinstance(ichi_result, tuple) else ichi_result
            if ichi_df is None or ichi_df.empty:
                raise ValueError("Empty ichimoku result")
            cols = list(ichi_df.columns)

            def _get_col(prefix):
                return next((c for c in cols if c.upper().startswith(prefix.upper())), None)

            tenkan_col = _get_col("ITS")
            kijun_col  = _get_col("IKS")
            span_a_col = _get_col("ISA")
            span_b_col = _get_col("ISB")

            tenkan = _safe_float(ichi_df[tenkan_col].iloc[-1]) if tenkan_col else None
            kijun  = _safe_float(ichi_df[kijun_col].iloc[-1])  if kijun_col  else None
            span_a = _safe_float(ichi_df[span_a_col].iloc[-1]) if span_a_col else None
            span_b = _safe_float(ichi_df[span_b_col].iloc[-1]) if span_b_col else None
            source = "pandas_ta"

        except ImportError:
            # Fallback: pure pandas
            t_series, k_series, sa_series, sb_series = _ichimoku_pure_pandas(df)
            tenkan = _safe_float(t_series.iloc[-1])
            kijun  = _safe_float(k_series.iloc[-1])
            span_a = _safe_float(sa_series.iloc[-1])
            span_b = _safe_float(sb_series.iloc[-1])

        # If kijun still None, use TV BLine as fallback
        if kijun is None:
            kijun = _safe_float(ind.get("Ichimoku.BLine"))

        # Price vs Cloud
        price = _safe_float(close.iloc[-1])
        price_vs_cloud = "UNKNOWN"
        cloud_signal   = "NEUTRAL"

        if price is not None and span_a is not None and span_b is not None:
            cloud_top = max(span_a, span_b)
            cloud_bot = min(span_a, span_b)
            if price > cloud_top:
                price_vs_cloud = "ABOVE"
                cloud_signal = "BULLISH"
            elif price < cloud_bot:
                price_vs_cloud = "BELOW"
                cloud_signal = "BEARISH"
            else:
                price_vs_cloud = "INSIDE"
                cloud_signal = "NEUTRAL"

        return {
            "tenkan_sen":    tenkan,
            "kijun_sen":     kijun,
            "senkou_span_a": span_a,
            "senkou_span_b": span_b,
            "price_vs_cloud": price_vs_cloud,
            "signal":        cloud_signal,
            "_source":       source,
        }

    except Exception as e:
        # Last resort: return what we can from TV BLine
        kijun = _safe_float(ind.get("Ichimoku.BLine"))
        return {
            "tenkan_sen":    None,
            "kijun_sen":     kijun,
            "senkou_span_a": None,
            "senkou_span_b": None,
            "price_vs_cloud": "UNKNOWN",
            "signal":        "NEUTRAL",
            "error":         str(e),
        }


# ── Volume Profile ────────────────────────────────────────────────────────────

def _build_volume_profile(df, n_bins: int = 20) -> dict:
    """
    Compute Volume Profile from OHLCV data.
    - POC: price level with highest volume
    - VAH/VAL: Value Area High/Low (70% of total volume)
    """
    try:
        import numpy as np  # type: ignore

        # squeeze handles yfinance MultiIndex (single-ticker returns DataFrame, not Series)
        import pandas as _pd
        _c = df["Close"]
        _v = df["Volume"]
        if isinstance(_c, _pd.DataFrame):
            _c = _c.iloc[:, 0]
        if isinstance(_v, _pd.DataFrame):
            _v = _v.iloc[:, 0]
        _c = _c.dropna()
        _v = _v.reindex(_c.index).fillna(0)
        close  = _c.values.astype(float)
        volume = _v.values.astype(float)

        price_min = float(close.min())
        price_max = float(close.max())

        if price_min == price_max or len(close) < 5:
            raise ValueError("No price range in data")

        # Build bins
        bins    = np.linspace(price_min, price_max, n_bins + 1)
        bin_vol = np.zeros(n_bins)

        for i in range(len(close)):
            idx = int((close[i] - price_min) / (price_max - price_min) * n_bins)
            idx = max(0, min(n_bins - 1, idx))
            bin_vol[idx] += volume[i]

        bin_mid = (bins[:-1] + bins[1:]) / 2

        # POC: bin with maximum volume
        poc_idx = int(np.argmax(bin_vol))
        poc     = float(bin_mid[poc_idx])

        # Value Area: 70% of total volume
        total_vol = float(bin_vol.sum())
        target    = total_vol * 0.70

        # Sort bins by volume descending, accumulate
        sorted_idx = np.argsort(bin_vol)[::-1]
        accum      = 0.0
        va_indices = []
        for i in sorted_idx:
            accum += bin_vol[i]
            va_indices.append(i)
            if accum >= target:
                break

        va_prices = bin_mid[va_indices]
        vah = float(va_prices.max())
        val = float(va_prices.min())

        # Current price vs POC
        current_price = float(close[-1])
        threshold = (price_max - price_min) / n_bins
        if current_price > poc + threshold:
            price_vs_poc = "ABOVE_POC"
        elif current_price < poc - threshold:
            price_vs_poc = "BELOW_POC"
        else:
            price_vs_poc = "AT_POC"

        return {
            "poc":             round(poc, 2),
            "vah":             round(vah, 2),
            "val":             round(val, 2),
            "value_area_pct":  70.0,
            "price_vs_poc":    price_vs_poc,
        }

    except Exception as e:
        return {
            "poc":            None,
            "vah":            None,
            "val":            None,
            "value_area_pct": 70.0,
            "price_vs_poc":   "UNKNOWN",
            "error":          str(e),
        }


# ── Main service function ─────────────────────────────────────────────────────

def get_advanced_indicators_for_stock(ticker: str, timeframe: str = "1D") -> dict:
    """
    Indikator teknikal lanjutan: ADX/DMI, CCI, Williams %R, StochRSI,
    Stochastic Slow (10,5,5), Ichimoku Cloud, Volume Profile (POC/VAH/VAL).

    Lebih lengkap dari get_stock_decision — khusus untuk analisis mendalam.
    Ticker: kode saham IDX (BBCA, TLKM, dll). Timeframe: 1D (default), 1W, 4H.
    """
    clean   = _clean_ticker(ticker)
    full_symbol = f"IDX:{clean}"
    tf      = (timeframe or "1D").strip().upper()

    result: dict = {
        "ticker":    clean,
        "timeframe": tf,
        "price":     None,
    }

    # ── 1. Fetch tradingview_ta data ─────────────────────────────────────────
    ind: dict = {}
    if _TA_AVAILABLE:
        try:
            analysis = _get_multiple_analysis(
                screener=_IDX_SCREENER,
                interval=tf,
                symbols=[full_symbol],
            )
            if full_symbol in analysis and analysis[full_symbol] is not None:
                ind = analysis[full_symbol].indicators
                result["price"] = _safe_float(ind.get("close"))
        except Exception as e:
            result["tv_error"] = str(e)
    else:
        result["tv_error"] = "tradingview_ta not available"

    # ── 2. Fetch yfinance OHLCV ──────────────────────────────────────────────
    df = None
    try:
        import yfinance as yf  # type: ignore

        yf_symbol = f"{clean}.JK"
        df = yf.download(
            yf_symbol,
            period="3mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df is not None and not df.empty:
            # If price not set from TV, use yfinance
            if result["price"] is None:
                result["price"] = _safe_float(float(df["Close"].iloc[-1]))
    except Exception as e:
        result["yf_error"] = str(e)

    # ── 3. Build each indicator block ────────────────────────────────────────

    # ADX/DMI (from tradingview_ta)
    try:
        result["adx_dmi"] = _build_adx_dmi(ind)
    except Exception as e:
        result["adx_dmi"] = {"error": str(e)}

    # CCI (from tradingview_ta)
    try:
        result["cci"] = _build_cci(ind)
    except Exception as e:
        result["cci"] = {"error": str(e)}

    # Williams %R (from tradingview_ta)
    try:
        result["williams_r"] = _build_williams_r(ind)
    except Exception as e:
        result["williams_r"] = {"error": str(e)}

    # StochRSI (from tradingview_ta)
    try:
        result["stoch_rsi"] = _build_stoch_rsi(ind)
    except Exception as e:
        result["stoch_rsi"] = {"error": str(e)}

    # Stoch Slow 10,5,5 (yfinance + pandas_ta)
    if df is not None and not df.empty:
        try:
            result["stoch_slow"] = _build_stoch_slow(df)
        except Exception as e:
            result["stoch_slow"] = {"k": None, "d": None, "signal": "ERROR", "error": str(e)}
    else:
        result["stoch_slow"] = {"k": None, "d": None, "signal": "NO_DATA",
                                 "error": "yfinance data unavailable"}

    # Ichimoku (yfinance + pandas_ta, with TV BLine fallback)
    if df is not None and not df.empty:
        try:
            result["ichimoku"] = _build_ichimoku(df, ind)
        except Exception as e:
            result["ichimoku"] = {
                "tenkan_sen": None, "kijun_sen": _safe_float(ind.get("Ichimoku.BLine")),
                "senkou_span_a": None, "senkou_span_b": None,
                "price_vs_cloud": "UNKNOWN", "signal": "NEUTRAL",
                "error": str(e),
            }
    else:
        result["ichimoku"] = {
            "tenkan_sen": None,
            "kijun_sen": _safe_float(ind.get("Ichimoku.BLine")),
            "senkou_span_a": None, "senkou_span_b": None,
            "price_vs_cloud": "UNKNOWN", "signal": "NEUTRAL",
            "error": "yfinance data unavailable",
        }

    # Volume Profile (yfinance OHLCV)
    if df is not None and not df.empty:
        try:
            result["volume_profile"] = _build_volume_profile(df)
        except Exception as e:
            result["volume_profile"] = {
                "poc": None, "vah": None, "val": None,
                "value_area_pct": 70.0, "price_vs_poc": "UNKNOWN",
                "error": str(e),
            }
    else:
        result["volume_profile"] = {
            "poc": None, "vah": None, "val": None,
            "value_area_pct": 70.0, "price_vs_poc": "UNKNOWN",
            "error": "yfinance data unavailable",
        }

    return result
