"""
IDX Fundamental Screener — powered by tradingview-screener.

Pulls fundamental columns (market cap, P/E, P/B, ROE, dividend yield,
debt/equity, revenue growth, margins, EPS, etc.) for all ~860 IDX stocks
in a single API call. Supports sort, filter, and sector targeting.
"""
from __future__ import annotations

import math
from typing import Optional

try:
    from tradingview_screener import Query
    from tradingview_screener.column import Column
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# ── Column set ────────────────────────────────────────────────────────────────

_FUNDAMENTAL_COLS = [
    "name",
    "close",
    "volume",
    "change|1D",
    "market_cap_basic",
    "price_earnings_ttm",
    "price_book_ratio",
    "price_sales_ratio",
    "return_on_equity",
    "dividends_yield",
    "debt_to_equity",
    "revenue_growth_ttm",
    "earnings_per_share_basic_ttm",
    "gross_margin",
    "net_margin",
    "current_ratio",
    "total_revenue",
    "total_debt",
    "sector",
    "industry",
]

# Column → human label for display
_SORT_ALIASES: dict[str, str] = {
    "market_cap":       "market_cap_basic",
    "pe":               "price_earnings_ttm",
    "pb":               "price_book_ratio",
    "ps":               "price_sales_ratio",
    "roe":              "return_on_equity",
    "dividend_yield":   "dividends_yield",
    "de":               "debt_to_equity",
    "revenue_growth":   "revenue_growth_ttm",
    "eps":              "earnings_per_share_basic_ttm",
    "gross_margin":     "gross_margin",
    "net_margin":       "net_margin",
    "current_ratio":    "current_ratio",
    "change":           "change|1D",
    "price":            "close",
    "volume":           "volume",
}


def _safe(v) -> Optional[float]:
    """Return None for NaN/inf, otherwise round to 4dp."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe(v)
    return int(f) if f is not None else None


def screen_idx_fundamental(
    sort_by: str = "market_cap",
    ascending: bool = False,
    limit: int = 50,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    max_pe: Optional[float] = None,
    min_roe: Optional[float] = None,
    min_dividend_yield: Optional[float] = None,
    max_de: Optional[float] = None,
    min_revenue_growth: Optional[float] = None,
) -> dict:
    """
    Screen IDX stocks by fundamental criteria.

    Args:
        sort_by:             Column to sort by. Aliases: market_cap, pe, pb, ps,
                             roe, dividend_yield, de, revenue_growth, eps,
                             gross_margin, net_margin, current_ratio, change, price, volume.
        ascending:           Sort direction (default: descending).
        limit:               Max results (default 50, max 260).
        sector:              Filter by sector substring (case-insensitive), e.g. "Finance",
                             "Technology", "Consumer", "Energy", "Healthcare", "Utilities".
        min_market_cap:      Minimum market cap in IDR trillion (e.g. 1.0 = 1T IDR).
        max_pe:              Maximum P/E ratio.
        min_roe:             Minimum ROE % (e.g. 15 = 15%).
        min_dividend_yield:  Minimum dividend yield % (e.g. 3 = 3%).
        max_de:              Maximum Debt/Equity ratio.
        min_revenue_growth:  Minimum revenue growth % TTM.

    Returns:
        Dict with metadata + list of stocks with full fundamental data.
    """
    if not _AVAILABLE:
        return {"error": "tradingview-screener is not installed. Run `uv sync` or `pip install tradingview-screener`."}

    # Resolve sort column
    sort_col = _SORT_ALIASES.get(sort_by.lower(), sort_by)

    try:
        q = (
            Query()
            .set_markets("indonesia")
            .select(*_FUNDAMENTAL_COLS)
            .order_by(sort_col, ascending=ascending)
            .limit(min(limit, 500))
        )

        # Apply screener-side filters where tradingview_screener supports them
        if min_market_cap is not None:
            # Convert trillion IDR → raw IDR
            q = q.where(Column("market_cap_basic") >= min_market_cap * 1_000_000_000_000)
        if max_pe is not None:
            q = q.where(Column("price_earnings_ttm") <= max_pe)
            q = q.where(Column("price_earnings_ttm") > 0)
        if min_roe is not None:
            q = q.where(Column("return_on_equity") >= min_roe)
        if min_dividend_yield is not None:
            q = q.where(Column("dividends_yield") >= min_dividend_yield)
        if max_de is not None:
            q = q.where(Column("debt_to_equity") <= max_de)
        if min_revenue_growth is not None:
            q = q.where(Column("revenue_growth_ttm") >= min_revenue_growth)

        total, df = q.get_scanner_data()

        if df is None or df.empty:
            return {"total_available": 0, "returned": 0, "stocks": []}

        stocks = []
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).replace("IDX:", "")

            # Sector filter (post-query, substring match)
            row_sector = str(row.get("sector") or "")
            if sector and sector.lower() not in row_sector.lower():
                continue

            mc_raw = _safe(row.get("market_cap_basic"))
            mc_t = round(mc_raw / 1_000_000_000_000, 2) if mc_raw else None  # IDR trillion

            rev_raw = _safe(row.get("total_revenue"))
            rev_b = round(rev_raw / 1_000_000_000, 1) if rev_raw else None  # IDR billion

            debt_raw = _safe(row.get("total_debt"))
            debt_b = round(debt_raw / 1_000_000_000, 1) if debt_raw else None  # IDR billion

            div_yield = _safe(row.get("dividends_yield"))

            stocks.append({
                "ticker":               ticker,
                "name":                 str(row.get("name") or ticker),
                "price":                _safe(row.get("close")),
                "change_1d_pct":        _safe(row.get("change|1D")),
                "volume":               _safe_int(row.get("volume")),
                "market_cap_idr_t":     mc_t,
                "pe_ttm":               _safe(row.get("price_earnings_ttm")),
                "pb":                   _safe(row.get("price_book_ratio")),
                "ps":                   _safe(row.get("price_sales_ratio")),
                "roe_pct":              _safe(row.get("return_on_equity")),
                "dividend_yield_pct":   round(div_yield, 2) if div_yield is not None else None,
                "debt_equity":          _safe(row.get("debt_to_equity")),
                "revenue_growth_pct":   _safe(row.get("revenue_growth_ttm")),
                "eps_ttm":              _safe(row.get("earnings_per_share_basic_ttm")),
                "gross_margin_pct":     _safe(row.get("gross_margin")),
                "net_margin_pct":       _safe(row.get("net_margin")),
                "current_ratio":        _safe(row.get("current_ratio")),
                "revenue_idr_b":        rev_b,
                "total_debt_idr_b":     debt_b,
                "sector":               row_sector or None,
                "industry":             str(row.get("industry") or "") or None,
            })

        # Applied filters summary for context
        applied_filters = {}
        if sector:
            applied_filters["sector"] = sector
        if min_market_cap is not None:
            applied_filters["min_market_cap_t"] = min_market_cap
        if max_pe is not None:
            applied_filters["max_pe"] = max_pe
        if min_roe is not None:
            applied_filters["min_roe_pct"] = min_roe
        if min_dividend_yield is not None:
            applied_filters["min_dividend_yield_pct"] = min_dividend_yield
        if max_de is not None:
            applied_filters["max_debt_equity"] = max_de
        if min_revenue_growth is not None:
            applied_filters["min_revenue_growth_pct"] = min_revenue_growth

        return {
            "total_available":  total,
            "returned":         len(stocks),
            "sorted_by":        sort_col,
            "ascending":        ascending,
            "filters_applied":  applied_filters,
            "stocks":           stocks,
        }

    except Exception as exc:
        return {"error": f"Screener query failed: {exc}"}
