"""
IDX Stock Decision Engine — get_stock_decision untuk Bursa Efek Indonesia.

Menggabungkan 3-layer Technical Scoring (compute_stock_score / compute_trade_setup /
compute_trade_quality) dengan Bandarmology Signal (OBV / CMF / MFI / VWAP /
divergence detection) untuk menghasilkan keputusan BUY / HOLD / SELL / AVOID
yang komprehensif.

Arsitektur:
    Layer A–D  : Technical scoring 100 poin (dari indicators.py)
    Layer E    : Bandarmology signal dari yfinance OHLCV
    Liquidity  : IDR-calibrated threshold (berbeda dari EGP di egx_service)
    Output     : Decision + Grade + Score + Trade Setup + Bandar Context
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# ── tradingview_ta ─────────────────────────────────────────────────────────────
try:
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as _get_multiple_analysis,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

# ── yfinance ───────────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

from tradingview_mcp.core.services.indicators import (
    compute_stock_score,
    compute_trade_setup,
    compute_trade_quality,
    compute_metrics,
    extract_extended_indicators,
)

# ── tradingview-screener ───────────────────────────────────────────────────────
try:
    from tradingview_screener import Query
    _SCREENER_AVAILABLE = True
except ImportError:
    _SCREENER_AVAILABLE = False

# ── constants ──────────────────────────────────────────────────────────────────
_IDX_SCREENER = "indonesia"

# IDR liquidity thresholds (average daily traded value = avg_vol * close)
# Berbeda jauh dari EGP:  1 USD ≈ 16,000 IDR
_IDR_VAL_FLOOR  = 100_000_000      # 100 juta IDR/hari  → hampir tidak liquid
_IDR_VAL_LOW    = 500_000_000      # 500 juta IDR/hari  → tipis
_IDR_VAL_MODEST = 2_000_000_000    # 2 miliar IDR/hari  → cukup liquid
_IDR_VOL_FLOOR  = 50_000           # 50K lembar/hari    → minimal
_IDR_VOL_LOW    = 200_000          # 200K lembar/hari   → masih tipis

# ── module-level cache untuk IDX universe change ───────────────────────────────
# Cache berlaku selama session (dict kosong = belum di-fetch)
# Key: "data" → list[float], "ticker_map" → dict[str, float]
_IDX_UNIVERSE_CACHE: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Bandarmology (yfinance-based)
# ══════════════════════════════════════════════════════════════════════════════

def _clean_ticker(ticker: str) -> str:
    return re.sub(r"\.JK$", "", ticker.strip().upper())


def _yf_ticker(ticker: str) -> str:
    t = _clean_ticker(ticker)
    return t if t.endswith(".JK") else f"{t}.JK"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Cross-sectional percentile rank (Layer A4)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_idx_universe_changes() -> tuple[list[float], dict[str, float]]:
    """
    Scan seluruh IDX universe dan ambil % change hari ini dari TV screener.

    Returns:
        (all_changes, ticker_map) — list semua changes + dict ticker→change
        Cache di module-level, di-refresh per session.
    """
    if _IDX_UNIVERSE_CACHE.get("data"):
        return _IDX_UNIVERSE_CACHE["data"], _IDX_UNIVERSE_CACHE["ticker_map"]

    if not _SCREENER_AVAILABLE:
        return [], {}

    try:
        _, df = (
            Query()
            .set_markets("indonesia")
            .select("change", "volume")
            .limit(1100)          # IDX punya ~900 saham aktif
            .get_scanner_data()
        )
    except Exception:
        return [], {}

    if df is None or df.empty or "change" not in df.columns:
        return [], {}

    # ticker kolom format: "IDX:BBCA" → strip prefix
    ticker_map: dict[str, float] = {}
    for _, row in df.iterrows():
        raw_ticker = str(row.get("ticker", ""))
        change_val = row.get("change")
        if change_val is None:
            continue
        # Strip exchange prefix jika ada
        short = raw_ticker.split(":")[-1]
        try:
            ticker_map[short] = float(change_val)
        except (ValueError, TypeError):
            continue

    all_changes = list(ticker_map.values())

    _IDX_UNIVERSE_CACHE["data"]       = all_changes
    _IDX_UNIVERSE_CACHE["ticker_map"] = ticker_map
    return all_changes, ticker_map


def _fetch_idx_change_rank(ticker: str) -> Optional[float]:
    """
    Hitung percentile rank (0.0–1.0) dari % change saham vs seluruh universe IDX.

    0.0 = paling bawah (worst performer hari ini)
    1.0 = paling atas (top performer hari ini)

    Returns None jika data tidak tersedia.
    """
    all_changes, ticker_map = _fetch_idx_universe_changes()
    if not all_changes:
        return None

    clean = _clean_ticker(ticker)
    stock_change = ticker_map.get(clean)
    if stock_change is None:
        # Fallback: ambil dari screener direct untuk saham ini
        try:
            _, df = (
                Query()
                .set_markets("indonesia")
                .select("change")
                .set_tickers([f"IDX:{clean}"])
                .get_scanner_data()
            )
            if not df.empty:
                stock_change = float(df.iloc[0]["change"])
        except Exception:
            return None

    if stock_change is None:
        return None

    count_below = sum(1 for c in all_changes if c < stock_change)
    pct_rank = count_below / len(all_changes)
    return round(pct_rank, 4)


def _calc_obv(hist: pd.DataFrame) -> pd.Series:
    closes  = hist["Close"].values
    volumes = hist["Volume"].values
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=hist.index)


def _calc_cmf(hist: pd.DataFrame, window: int = 20) -> pd.Series:
    clv = ((hist["Close"] - hist["Low"]) - (hist["High"] - hist["Close"])) / (
        hist["High"] - hist["Low"] + 1e-9
    )
    mfv = clv * hist["Volume"]
    return (
        mfv.rolling(window, min_periods=5).sum()
        / hist["Volume"].rolling(window, min_periods=5).sum()
    )


def _calc_mfi(hist: pd.DataFrame, window: int = 14) -> pd.Series:
    tp  = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    mf  = tp * hist["Volume"]
    pos = mf.where(tp > tp.shift(1), 0)
    neg = mf.where(tp < tp.shift(1), 0)
    pos_sum = pos.rolling(window, min_periods=5).sum()
    neg_sum = neg.rolling(window, min_periods=5).sum()
    mfr = pos_sum / (neg_sum + 1e-9)
    return 100 - (100 / (1 + mfr))


def _calc_vwap(hist: pd.DataFrame) -> pd.Series:
    tp      = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    cum_tpv = (tp * hist["Volume"]).rolling(20, min_periods=5).sum()
    cum_vol = hist["Volume"].rolling(20, min_periods=5).sum()
    return cum_tpv / (cum_vol + 1e-9)


def _money_flow_signal(
    cmf: float, mfi: float, obv_trend_pct: float, vwap_dev_pct: float
) -> dict:
    score = 0

    if cmf > 0.15:    score += 2
    elif cmf > 0.05:  score += 1
    elif cmf < -0.15: score -= 2
    elif cmf < -0.05: score -= 1

    if mfi > 80:     score += 1
    elif mfi > 60:   score += 2
    elif mfi < 20:   score -= 1
    elif mfi < 40:   score -= 2

    if obv_trend_pct > 10:    score += 2
    elif obv_trend_pct > 2:   score += 1
    elif obv_trend_pct < -10: score -= 2
    elif obv_trend_pct < -2:  score -= 1

    if vwap_dev_pct > 3:    score += 2
    elif vwap_dev_pct > 1:  score += 1
    elif vwap_dev_pct < -3: score -= 2
    elif vwap_dev_pct < -1: score -= 1

    normalized = round((score / 8) * 100, 1)

    if score >= 5:    label = "STRONG BUY — Uang masuk deras"
    elif score >= 2:  label = "BUY — Tekanan beli dominan"
    elif score >= -1: label = "NEUTRAL — Flow seimbang"
    elif score >= -4: label = "SELL — Tekanan jual dominan"
    else:             label = "STRONG SELL — Uang keluar deras"

    return {"score": normalized, "label": label, "raw_score": score}


def _detect_divergence(
    hist: pd.DataFrame,
    obv_series: pd.Series,
    cmf_series: pd.Series,
    mfi_series: pd.Series,
    window: int = 10,
) -> dict:
    n = min(window * 2, len(hist))
    if n < 10:
        return {"detected": False, "signals": [], "bias": "UNKNOWN",
                "summary": "Data tidak cukup untuk deteksi divergence"}

    chunk = hist.tail(n)
    half  = n // 2

    price_early  = chunk["Close"].iloc[:half].mean()
    price_recent = chunk["Close"].iloc[half:].mean()
    price_up   = price_recent > price_early * 1.005
    price_down = price_recent < price_early * 0.995

    obv_chunk  = obv_series.iloc[-n:]
    obv_early  = obv_chunk.iloc[:half].mean()
    obv_recent = obv_chunk.iloc[half:].mean()
    obv_up   = obv_recent > obv_early * 1.02
    obv_down = obv_recent < obv_early * 0.98

    cmf_chunk = cmf_series.iloc[-n:].dropna()
    if len(cmf_chunk) >= 4:
        cmf_early  = cmf_chunk.iloc[:len(cmf_chunk) // 2].mean()
        cmf_recent = cmf_chunk.iloc[len(cmf_chunk) // 2:].mean()
        cmf_up   = cmf_recent > cmf_early + 0.03
        cmf_down = cmf_recent < cmf_early - 0.03
    else:
        cmf_up = cmf_down = False

    mfi_chunk = mfi_series.iloc[-n:].dropna()
    if len(mfi_chunk) >= 4:
        mfi_early  = mfi_chunk.iloc[:len(mfi_chunk) // 2].mean()
        mfi_recent = mfi_chunk.iloc[len(mfi_chunk) // 2:].mean()
        mfi_up   = mfi_recent > mfi_early + 3
        mfi_down = mfi_recent < mfi_early - 3
    else:
        mfi_up = mfi_down = False

    signals = []

    if price_up:
        if obv_down:
            signals.append({"type": "BEARISH", "indicator": "OBV",
                "detail": "Harga naik tapi OBV turun — volume tidak konfirmasi rally",
                "severity": "HIGH"})
        if cmf_down:
            signals.append({"type": "BEARISH", "indicator": "CMF",
                "detail": "Harga naik tapi CMF turun — tekanan beli melemah",
                "severity": "MODERATE"})
        if mfi_down:
            signals.append({"type": "BEARISH", "indicator": "MFI",
                "detail": "Harga naik tapi MFI turun — money flow melemah",
                "severity": "MODERATE"})

    if price_down:
        if obv_up:
            signals.append({"type": "BULLISH", "indicator": "OBV",
                "detail": "Harga turun tapi OBV naik — ada akumulasi tersembunyi",
                "severity": "HIGH"})
        if cmf_up:
            signals.append({"type": "BULLISH", "indicator": "CMF",
                "detail": "Harga turun tapi CMF naik — tekanan beli diam-diam meningkat",
                "severity": "MODERATE"})
        if mfi_up:
            signals.append({"type": "BULLISH", "indicator": "MFI",
                "detail": "Harga turun tapi MFI naik — smart money mulai masuk",
                "severity": "MODERATE"})

    bullish_count = sum(1 for s in signals if s["type"] == "BULLISH")
    bearish_count = sum(1 for s in signals if s["type"] == "BEARISH")
    high_count    = sum(1 for s in signals if s["severity"] == "HIGH")

    if not signals:
        summary = "No divergence — harga dan indikator konfirmasi satu sama lain"
        bias    = "CONFIRMED"
    elif bullish_count > bearish_count:
        summary = f"BULLISH DIVERGENCE ({bullish_count} signal) — potensi akumulasi tersembunyi"
        bias    = "BULLISH_DIV"
    elif bearish_count > bullish_count:
        summary = f"BEARISH DIVERGENCE ({bearish_count} signal) — waspadai distribusi"
        bias    = "BEARISH_DIV"
    else:
        summary = "MIXED signals — konflik antar indikator"
        bias    = "MIXED"

    return {
        "detected": len(signals) > 0,
        "bias": bias,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "high_severity_count": high_count,
        "signals": signals,
        "summary": summary,
    }


def _fetch_bandar_signal(ticker: str, period: str = "3mo") -> dict:
    """
    Ambil data yfinance dan hitung bandarmology indicators.
    Return dict dengan money_flow, divergence, dan score_adjustment.
    """
    if not _YF_AVAILABLE:
        return {"available": False, "error": "yfinance tidak terinstall"}

    yf_tick = _yf_ticker(ticker)
    try:
        hist = yf.download(yf_tick, period=period, interval="1d",
                           progress=False, auto_adjust=True)
    except Exception as e:
        return {"available": False, "error": str(e)}

    if hist is None or len(hist) < 20:
        return {"available": False, "error": f"Data tidak cukup ({len(hist) if hist is not None else 0} bars)"}

    # Flatten MultiIndex columns jika ada
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)

    try:
        obv_series = _calc_obv(hist)
        cmf_series = _calc_cmf(hist)
        mfi_series = _calc_mfi(hist)
        vwap_series = _calc_vwap(hist)

        cmf_val  = float(cmf_series.iloc[-1])
        mfi_val  = float(mfi_series.iloc[-1])
        vwap_val = float(vwap_series.iloc[-1])
        close    = float(hist["Close"].iloc[-1])

        # OBV trend: bandingkan rata-rata 5 bar terakhir vs 5 bar sebelumnya
        obv_recent = obv_series.iloc[-5:].mean()
        obv_prev   = obv_series.iloc[-10:-5].mean()
        obv_trend_pct = ((obv_recent - obv_prev) / (abs(obv_prev) + 1e-9)) * 100

        # VWAP deviation
        vwap_dev_pct = ((close - vwap_val) / vwap_val) * 100 if vwap_val > 0 else 0.0

        money_flow = _money_flow_signal(cmf_val, mfi_val, obv_trend_pct, vwap_dev_pct)
        divergence = _detect_divergence(hist, obv_series, cmf_series, mfi_series, window=10)

        # ── Score adjustment untuk 100-poin system ──────────────────────────
        # Money flow: raw_score -8..+8 → scale ke -20..+20
        mf_adj = round((money_flow["raw_score"] / 8) * 20)

        # Divergence adjustment
        div_adj = 0
        if divergence["detected"]:
            high_sev = divergence["high_severity_count"]
            if divergence["bias"] == "BULLISH_DIV":
                div_adj = min(10, high_sev * 6 + divergence["bullish_count"] * 2)
            elif divergence["bias"] == "BEARISH_DIV":
                div_adj = -min(10, high_sev * 6 + divergence["bearish_count"] * 2)

        total_adj = max(-25, min(25, mf_adj + div_adj))

        return {
            "available": True,
            "indicators": {
                "obv_trend_pct": round(obv_trend_pct, 2),
                "obv_direction": "UP" if obv_trend_pct > 2 else "DOWN" if obv_trend_pct < -2 else "FLAT",
                "cmf": round(cmf_val, 4),
                "cmf_signal": "BUYING" if cmf_val > 0.05 else "SELLING" if cmf_val < -0.05 else "NEUTRAL",
                "mfi": round(mfi_val, 1),
                "mfi_zone": "OVERBOUGHT" if mfi_val > 80 else "BULLISH" if mfi_val > 60 else
                            "OVERSOLD" if mfi_val < 20 else "BEARISH" if mfi_val < 40 else "NEUTRAL",
                "vwap": round(vwap_val, 0),
                "vwap_deviation_pct": round(vwap_dev_pct, 2),
                "vwap_position": "ABOVE" if vwap_dev_pct > 0 else "BELOW",
            },
            "money_flow": money_flow,
            "divergence": divergence,
            "score_adjustment": total_adj,
            "bars_analyzed": len(hist),
        }

    except Exception as e:
        return {"available": False, "error": f"Kalkulasi gagal: {e}"}


def _idr_liquidity_check(avg_vol: float, close: float) -> dict:
    """
    IDR-calibrated liquidity assessment.
    avg_vol  : average daily volume (shares/hari)
    close    : harga saham (IDR)
    """
    avg_value_idr = avg_vol * close
    warnings = []
    grade_cap = None
    penalty   = 0

    # Threshold berbasis traded value (IDR/hari)
    if avg_value_idr < _IDR_VAL_FLOOR:
        penalty   = 20
        grade_cap = "Avoid"
        warnings.append(f"Traded value sangat rendah ({avg_value_idr/1e6:.0f} juta IDR/hari)")
    elif avg_value_idr < _IDR_VAL_LOW:
        penalty   = 10
        grade_cap = "Watchlist"
        warnings.append(f"Traded value rendah ({avg_value_idr/1e6:.0f} juta IDR/hari)")
    elif avg_value_idr < _IDR_VAL_MODEST:
        penalty   = 3
        warnings.append(f"Traded value moderat ({avg_value_idr/1e6:.0f} juta IDR/hari)")

    # Threshold berbasis volume (shares/hari)
    if avg_vol < _IDR_VOL_FLOOR:
        penalty   = max(penalty, 15)
        grade_cap = "Avoid"
        warnings.append(f"Volume sangat tipis ({avg_vol:,.0f} lembar/hari)")
    elif avg_vol < _IDR_VOL_LOW and grade_cap is None:
        penalty   = max(penalty, 5)
        grade_cap = "Watchlist"
        warnings.append(f"Volume tipis ({avg_vol:,.0f} lembar/hari)")

    return {
        "avg_volume_20d": round(avg_vol),
        "avg_value_idr": round(avg_value_idr),
        "avg_value_formatted": f"Rp {avg_value_idr/1e9:.1f}M" if avg_value_idr >= 1e9
                                else f"Rp {avg_value_idr/1e6:.0f} juta",
        "liquidity_ok": grade_cap is None,
        "grade_cap": grade_cap,
        "penalty": penalty,
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def get_idx_stock_decision(ticker: str, timeframe: str = "1D") -> dict:
    """
    Keputusan investasi komprehensif untuk saham IDX.

    Menggabungkan:
    - Layer A–D : 100-poin technical scoring (EMA, RSI, MACD, ADX, ATR, Volume)
    - Layer E   : Bandarmology (OBV, CMF, MFI, VWAP, divergence) via yfinance
    - Liquidity : IDR-calibrated threshold

    Args:
        ticker   : Kode saham IDX (contoh: "BBCA", "TLKM", "ZATA")
        timeframe: TradingView interval — "1D" (default), "1W", "4H", dll.

    Returns:
        Dict lengkap dengan decision, score, grade, trade setup, dan bandar context.
    """
    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta tidak tersedia. Jalankan: uv sync"}

    clean = _clean_ticker(ticker)
    full_symbol = f"IDX:{clean}"
    tf = timeframe.strip().upper() or "1D"

    # ── 1. Fetch TA data via tradingview_ta ───────────────────────────────────
    try:
        analysis = _get_multiple_analysis(
            screener=_IDX_SCREENER,
            interval=tf,
            symbols=[full_symbol],
        )
    except Exception as exc:
        return {"error": f"Gagal fetch data TA untuk {full_symbol}: {exc}"}

    if full_symbol not in analysis or analysis[full_symbol] is None:
        return {"error": f"Tidak ada data untuk {full_symbol}. Pastikan ticker valid dan listed di IDX."}

    ind = analysis[full_symbol].indicators

    # Backfill ATR jika kosong
    if ind.get("ATR") is None:
        try:
            from tradingview_mcp.core.services.screener_provider import fetch_atr_for_ticker
            atr_val = fetch_atr_for_ticker(full_symbol, _IDX_SCREENER, tf)
            if atr_val is not None:
                ind["ATR"] = atr_val
        except Exception:
            pass

    metrics = compute_metrics(ind)
    if not metrics:
        return {"error": f"Tidak bisa compute metrics untuk {full_symbol}"}

    close    = ind.get("close", 0)
    vol      = ind.get("volume", 0) or 0
    vol_sma  = ind.get("volume.SMA20", 0) or 0

    # ── 2. IDR Liquidity check ─────────────────────────────────────────────────
    avg_vol_for_liq = vol_sma if vol_sma > 0 else vol
    liq = _idr_liquidity_check(avg_vol_for_liq, close)

    # ── 3. Layer A–D: 3-layer stock scoring ───────────────────────────────────
    # Fetch cross-sectional percentile rank dari TV screener (Layer A4)
    # None = tidak tersedia, compute_stock_score akan skip section ini
    change_pct_rank = _fetch_idx_change_rank(clean)

    # Gunakan currency="USD" agar compute_stock_score tidak apply EGP thresholds
    # (liquidity assessment kita override dengan IDR check di atas)
    score_result = compute_stock_score(ind, change_pct_rank=change_pct_rank, currency="USD")
    if not score_result:
        return {"error": f"Tidak bisa compute stock score untuk {full_symbol}"}

    # Override liquidity penalty dari compute_stock_score dengan IDR version
    base_score = score_result["score"]

    # Re-apply IDR liquidity penalty (replace USD-based penalty yang sudah masuk)
    # Tambahkan liquidity penalty ke score sebagai adjustment
    liq_penalty_delta = liq["penalty"]
    adj_score = max(0, min(100, base_score - liq_penalty_delta))

    # Apply IDR grade cap jika ada
    grade_order = ["Avoid", "Watchlist", "Strong", "Elite"]
    base_grade  = score_result["grade"]
    if liq["grade_cap"] and grade_order.index(base_grade) > grade_order.index(liq["grade_cap"]):
        final_grade = liq["grade_cap"]
        score_result["penalties"].append(
            f"Grade capped {base_grade} → {final_grade} (likuiditas IDR tidak cukup)"
        )
    else:
        final_grade = base_grade

    # ── 4. Layer E: Bandarmology signal ───────────────────────────────────────
    bandar = _fetch_bandar_signal(clean, period="3mo")

    bandar_adj = 0
    if bandar.get("available"):
        bandar_adj = bandar.get("score_adjustment", 0)

    # ── 5. Final composite score ───────────────────────────────────────────────
    final_score = max(0, min(100, adj_score + bandar_adj))

    # Re-derive grade dari final score (setelah bandar adjustment)
    if liq["grade_cap"]:
        # Tetap cap jika liquidity bermasalah
        if final_score >= 85:
            raw_grade = "Elite"
        elif final_score >= 70:
            raw_grade = "Strong"
        elif final_score >= 55:
            raw_grade = "Watchlist"
        else:
            raw_grade = "Avoid"
        if grade_order.index(raw_grade) > grade_order.index(liq["grade_cap"]):
            final_grade = liq["grade_cap"]
        else:
            final_grade = raw_grade
    else:
        if final_score >= 85:
            final_grade = "Elite"
        elif final_score >= 70:
            final_grade = "Strong"
        elif final_score >= 55:
            final_grade = "Watchlist"
        else:
            final_grade = "Avoid"

    # ── 6. Trade Setup (Layer B) ───────────────────────────────────────────────
    trade_setup  = None
    trade_quality = None
    if final_score >= 60:
        trade_setup = compute_trade_setup(ind)
        if trade_setup:
            trade_quality = compute_trade_quality(ind, final_score, trade_setup)

    # ── 7. Final decision ──────────────────────────────────────────────────────
    tq_score = trade_quality["trade_quality_score"] if trade_quality else 0
    rr2      = trade_setup["risk_reward"]["to_target_2"] if trade_setup else 0

    if final_score >= 70 and tq_score >= 65 and rr2 and rr2 >= 2.0:
        decision    = "BUY"
        confidence  = "HIGH"
        rec         = "QUALIFIED — Momentum kuat dengan setup tradeable"
    elif final_score >= 70 and (tq_score >= 50 or not trade_setup):
        decision    = "BUY"
        confidence  = "MODERATE"
        rec         = "CONDITIONAL — Saham kuat tapi setup perlu konfirmasi"
    elif final_score >= 55:
        decision    = "HOLD"
        confidence  = "MODERATE"
        rec         = "WATCHLIST — Pantau untuk entry yang lebih baik"
    elif final_score >= 40:
        decision    = "HOLD"
        confidence  = "LOW"
        rec         = "WEAK — Belum memenuhi kriteria momentum"
    else:
        decision    = "AVOID"
        confidence  = "HIGH"
        rec         = "AVOID — Tidak memenuhi syarat teknikal / likuiditas"

    # Bandarmology override: jika bandar STRONG SELL + bearish divergence → downgrade
    if bandar.get("available"):
        mf = bandar.get("money_flow", {})
        div = bandar.get("divergence", {})
        raw_mf_score = mf.get("raw_score", 0)
        if raw_mf_score <= -5 and div.get("bias") == "BEARISH_DIV":
            if decision == "BUY":
                decision   = "HOLD"
                confidence = "LOW"
                rec        = "DOWNGRADED — Bandar signal sangat bearish, tahan dulu"

    # ── 8. Extended indicators ────────────────────────────────────────────────
    extended = extract_extended_indicators(ind)

    # ── 8b. CIA Setup Detection ───────────────────────────────────────────────
    cia_context: dict = {}
    try:
        from tradingview_mcp.core.services.cia_scanner_service import _classify, _pct

        # SMA values sudah ada di ind (dari tradingview_ta)
        _close  = ind.get("close") or 0
        _ma5    = ind.get("SMA5")
        _ma10   = ind.get("SMA10")
        _ma20   = ind.get("SMA20")
        _ma50   = ind.get("SMA50")
        _ma100  = ind.get("SMA100")
        _ma200  = ind.get("SMA200")
        _vol    = ind.get("volume") or 0

        # Ambil V60 dari tradingview_screener (satu field, ringan)
        _avg_v60: Optional[float] = None
        try:
            from tradingview_screener import Query as _Q
            _, _sdf = _Q().set_markets("indonesia").select(
                "average_volume_60d_calc"
            ).set_tickers(f"IDX:{clean}").get_scanner_data()
            if not _sdf.empty:
                _avg_v60 = _sdf.iloc[0].get("average_volume_60d_calc")
        except Exception:
            pass

        if _close > 0:
            _setups, _dist = _classify(
                close=_close, ma5=_ma5, ma10=_ma10, ma20=_ma20,
                ma50=_ma50, ma100=_ma100, ma200=_ma200,
                volume=_vol, avg_vol=_avg_v60,
                tight_pct=5.0, kame_ratio=2.5,
            )

            # MA distance summary (format mirip CIAbot)
            _ma_info: dict = {}
            for _label, _ma_val in [("ma5",_ma5),("ma10",_ma10),("ma20",_ma20),
                                     ("ma50",_ma50),("ma100",_ma100),("ma200",_ma200)]:
                if _ma_val:
                    _d = _pct(_close, _ma_val)
                    _above = "↑" if (_d is not None and _d >= 0) else "↓"
                    _ma_info[_label] = {
                        "value": round(_ma_val, 2),
                        "pct_from_price": _d,
                        "position": _above,
                    }

            cia_context = {
                "setups"     : _setups,
                "has_setup"  : len(_setups) > 0,
                "ma_position": _ma_info,
                "vol_ratio_v60": _dist.get("vol_ratio_v60"),
                "note": (
                    "STAR: setup premium terkuat (ketat+kamehameha). "
                    "SUPERKETAT: semua MA rapat ≤5%, entry terbaik. "
                    "KETAT: salah satu MA rapat, tren mulai. "
                    "RAINBOW: di atas semua MA, no resistance."
                ) if _setups else "Tidak ada CIA setup aktif saat ini.",
            }
    except Exception as _cia_err:
        cia_context = {"error": str(_cia_err)}

    # ── 9. Assemble output ────────────────────────────────────────────────────
    output: dict = {
        "ticker"   : clean,
        "exchange" : "IDX",
        "timeframe": tf,
        "price"    : metrics["price"],

        # Decision
        "decision"      : decision,
        "confidence"    : confidence,
        "grade"         : final_grade,
        "recommendation": rec,

        # Scoring
        "scores": {
            "ta_base_score"    : base_score,
            "liq_penalty"      : -liq_penalty_delta,
            "bandar_adj"       : bandar_adj,
            "final_score"      : final_score,
            "score_breakdown"  : score_result.get("breakdown", {}),
            "change_pct_rank"  : change_pct_rank,          # 0.0=worst, 1.0=best vs IDX universe
            "universe_size"    : len(_IDX_UNIVERSE_CACHE.get("data", [])),
        },

        "trend_state"  : score_result.get("trend_state", "Unknown"),
        "change_pct"   : score_result.get("change_pct", 0),
        "signals"      : score_result.get("signals", []),
        "penalties"    : score_result.get("penalties", []),

        # Liquidity (IDR)
        "liquidity": liq,

        # Key technical indicators
        "indicators": {
            "rsi"  : extended["rsi"],
            "macd" : extended["macd"],
            "adx"  : extended["adx"],
            "ema"  : extended["ema"],
            "volume": extended["volume"],
            "bollinger_bands": extended["bollinger_bands"],
            "tv_recommendation": extended["tv_recommendation"],
        },

        # Layer E: Bandarmology
        "bandarmology": bandar,

        # Layer F: CIA Setup (Chronic Investor Academy)
        "cia_setup": cia_context,
    }

    # Trade setup (hanya jika score cukup)
    if trade_setup:
        output["trade_setup"] = {
            "setup_types"     : trade_setup["setup_types"],
            "entry_points"    : trade_setup["entry_points"],
            "stop_loss"       : trade_setup["stop_loss"],
            "stop_distance_pct": trade_setup["stop_distance_pct"],
            "targets"         : trade_setup["targets"],
            "risk_reward"     : trade_setup["risk_reward"],
            "supports"        : trade_setup["supports"],
            "resistances"     : trade_setup["resistances"],
        }
    if trade_quality:
        output["trade_quality"] = {
            "score"    : trade_quality["trade_quality_score"],
            "label"    : trade_quality["quality"],
            "breakdown": trade_quality["breakdown"],
            "notes"    : trade_quality["notes"],
        }

    output["disclaimer"] = "Untuk tujuan edukasi/informasi saja. Bukan saran investasi."
    return output
