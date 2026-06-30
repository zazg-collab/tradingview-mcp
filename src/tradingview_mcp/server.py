"""
TradingView MCP Server — routing layer only.

Each @mcp.tool() handler is responsible for:
  1. Validating / sanitising parameters
  2. Delegating to the appropriate service module
  3. Returning the result

No business logic lives here. All computation is in core/services/*.
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Service imports ────────────────────────────────────────────────────────────
from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.services.screener_service import (
    fetch_bollinger_analysis,
    fetch_trending_analysis,
    analyze_coin,
    scan_consecutive_candles,
    scan_advanced_candle_patterns_single_tf,
    fetch_multi_timeframe_patterns,
    run_multi_timeframe_analysis,
)
from tradingview_mcp.core.services.scanner_service import (
    volume_breakout_scan,
    volume_confirmation_analyze,
    smart_volume_scan,
)
from tradingview_mcp.core.services.multi_agent_service import run_multi_agent_analysis
from tradingview_mcp.core.services.egx_service import (
    get_egx_market_overview,
    scan_egx_sector,
    run_egx_sector_scanner,
    analyze_egx_index,
    screen_egx_stocks,
    generate_egx_trade_plan,
    analyze_egx_fibonacci,
)
from tradingview_mcp.core.services.sentiment_service import analyze_sentiment
from tradingview_mcp.core.services.news_service import fetch_news_summary
from tradingview_mcp.core.services.yahoo_finance_service import (
    get_price,
    get_market_snapshot,
)
from tradingview_mcp.core.services.bitcoin_market_service import get_bitcoin_market_pulse
from tradingview_mcp.core.services.extended_hours_service import get_extended_hours_price
from tradingview_mcp.core.services.options_service import (
    get_options_chain,
    get_unusual_options_activity,
)
from tradingview_mcp.core.services.futures_service import (
    get_futures_overview,
    get_futures_movers,
    get_futures_category_snapshot,
    get_futures_watchlist,
)
from tradingview_mcp.core.services.backtest_service import (
    run_backtest,
    compare_strategies as _compare_strategies,
    walk_forward_backtest,
    run_cia_backtest as _run_cia_backtest,
    compare_cia_strategies as _compare_cia_strategies,
)
from tradingview_mcp.core.services.idx_fundamental_service import screen_idx_fundamental
from tradingview_mcp.core.services.idx_decision_service import get_idx_stock_decision
from tradingview_mcp.core.services.idx_fibonacci_service import analyze_idx_fibonacci
from tradingview_mcp.core.services.advanced_indicators_service import (
    get_advanced_indicators_for_stock as _get_advanced_indicators,
)
from tradingview_mcp.core.services.idx_screener_service import (
    screen_idx_stocks,
    analyze_idx_index,
    get_idx_top_gainers,
)
from tradingview_mcp.core.services.signal_scan_service import (
    scan_by_signal as _scan_by_signal,
    AVAILABLE_SIGNALS,
)
from tradingview_mcp.core.services.cia_scanner_service import (
    scan_cia_setups as _scan_cia_setups,
)
from tradingview_mcp.core.services.telegram_service import (
    telegram_read_messages as _tg_read,
    telegram_stock_sentiment as _tg_sentiment,
    telegram_list_chats as _tg_list_chats,
    telegram_list_folders as _tg_list_folders,
    telegram_read_folder as _tg_read_folder,
    telegram_query_knowledge as _tg_query_kb,
    telegram_knowledge_stats as _tg_kb_stats,
    telegram_cia_alerts as _tg_cia_alerts,
)
from tradingview_mcp.core.services.vector_service import (
    semantic_search as _vec_search,
    vector_stats as _vec_stats,
)
from tradingview_mcp.core.utils.validators import (
    sanitize_timeframe,
    sanitize_exchange,
    normalize_tradingview_symbol,
    normalize_yahoo_symbol,
    is_stock_exchange,
)
from tradingview_mcp.core.errors import (
    BatchExecutionError,
    ErrorCode,
    make_error,
)

try:
    import tradingview_screener  # noqa: F401
    TRADINGVIEW_SCREENER_AVAILABLE = True
except ImportError:
    TRADINGVIEW_SCREENER_AVAILABLE = False


# ── MCP server instance ────────────────────────────────────────────────────────

mcp = FastMCP(
    name="TradingView Multi-Market Screener",
    instructions=(
        "Multi-market screener backed by TradingView. "
        "Supports crypto exchanges (KuCoin, Binance, Bybit, MEXC, etc.), stock markets "
        "(IDX Indonesia/BEI, EGX, BIST, NASDAQ, NYSE, Bursa Malaysia, HKEX, SSE, SZSE, TWSE, TPEX), "
        "and futures markets (CME, COMEX, NYMEX, CBOT — equity index, energy, metals, "
        "agriculture, rates, forex, crypto futures). "
        "Tools: top_gainers, top_losers, bollinger_scan, coin_analysis, multi_agent_analysis, "
        "volume_breakout_scanner, futures_market_overview, futures_top_movers, "
        "futures_category_snapshot, futures_watchlist, egx_market_overview, and more."
    ),
)


# ── Screener tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def top_gainers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25) -> list[dict] | dict:
    """Return top gainers for an exchange and timeframe using Bollinger Band analysis.

    Args:
        exchange: Exchange name — crypto: KUCOIN, BINANCE, BYBIT, MEXC; stocks: IDX (Indonesia/BEI), EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Number of rows to return (max 50)

    Returns:
        list[dict] on success. On total upstream failure returns a structured
        error envelope: ``{"error": {"code": "ALL_BATCHES_FAILED", ...}}``.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))
    try:
        rows = fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    except BatchExecutionError as e:
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(e),
            batches_attempted=e.batches_attempted,
            batches_failed=e.batches_failed,
            first_error=e.first_error,
        )
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


@mcp.tool()
def top_losers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25) -> list[dict] | dict:
    """Return top losers for an exchange and timeframe. Supports crypto (KUCOIN, BINANCE, MEXC) and stocks (IDX, EGX, BIST, NASDAQ).

    Returns ``list[dict]`` on success, or an error envelope on total upstream
    failure (``{"error": {"code": "ALL_BATCHES_FAILED", ...}}``).
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))
    try:
        rows = fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    except BatchExecutionError as e:
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(e),
            batches_attempted=e.batches_attempted,
            batches_failed=e.batches_failed,
            first_error=e.first_error,
        )
    rows.sort(key=lambda x: x["changePercent"])
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows[:limit]]


@mcp.tool()
def bollinger_scan(exchange: str = "KUCOIN", timeframe: str = "4h", bbw_threshold: float = None, limit: int = 50) -> list[dict]:
    """Scan for assets with the tightest Bollinger Band squeeze. Returns the N most compressed
    assets sorted by BBW ascending (tightest first). Works with crypto and stocks.

    No fixed threshold is applied by default — the list is ranked relatively,
    so results are always meaningful regardless of asset class (crypto vs stocks).
    Use bbw_threshold only if you want a hard upper-bound filter.

    Args:
        exchange: Exchange — crypto: KUCOIN, BINANCE, BYBIT, MEXC; stocks: IDX (Indonesia/BEI),
                  EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        bbw_threshold: Optional hard upper-bound for BBW. Leave unset for relative ranking.
        limit: Number of rows to return (max 100)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "4h")
    limit = max(1, min(limit, 100))
    rows = fetch_bollinger_analysis(exchange, timeframe=timeframe, bbw_filter=bbw_threshold, limit=limit)
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


@mcp.tool()
def rating_filter(exchange: str = "KUCOIN", timeframe: str = "5m", rating: int = 2, limit: int = 25) -> list[dict] | dict:
    """Filter coins by Bollinger Band rating.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, MEXC, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        rating: BB rating (-3 to +3): -3=Strong Sell, -2=Sell, -1=Weak Sell, 1=Weak Buy, 2=Buy, 3=Strong Buy
        limit: Number of rows to return (max 50)

    Returns ``list[dict]`` on success, or an error envelope on total upstream
    failure (``{"error": {"code": "ALL_BATCHES_FAILED", ...}}``).
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "5m")
    rating = max(-3, min(3, rating))
    limit = max(1, min(limit, 50))
    try:
        rows = fetch_trending_analysis(exchange, timeframe=timeframe, filter_type="rating", rating_filter=rating, limit=limit)
    except BatchExecutionError as e:
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(e),
            batches_attempted=e.batches_attempted,
            batches_failed=e.batches_failed,
            first_error=e.first_error,
        )
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


# ── Coin / asset analysis ──────────────────────────────────────────────────────

@mcp.tool()
def coin_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Get detailed analysis for a specific asset (coin or stock) on specified exchange and timeframe.

    Args:
        symbol: Symbol — crypto: "BTCUSDT", "ETHUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W, 1M)

    Returns:
        Detailed analysis with all indicators and metrics
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    return analyze_coin(symbol, exchange, timeframe)


# ── Candle pattern tools ───────────────────────────────────────────────────────

@mcp.tool()
def consecutive_candles_scan(
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    pattern_type: str = "bullish",
    candle_count: int = 3,
    min_growth: float = 2.0,
    limit: int = 20,
) -> dict:
    """Scan for coins with consecutive growing/shrinking candles pattern.

    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        timeframe: Time interval (5m, 15m, 1h, 4h)
        pattern_type: "bullish" (growing candles) or "bearish" (shrinking candles)
        candle_count: Number of consecutive candles to check (2-5)
        min_growth: Minimum growth percentage for each candle
        limit: Maximum number of results to return
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    candle_count = max(2, min(5, candle_count))
    min_growth = max(0.5, min(20.0, min_growth))
    limit = max(1, min(50, limit))
    return scan_consecutive_candles(exchange, timeframe, pattern_type, candle_count, min_growth, limit)


@mcp.tool()
def advanced_candle_pattern(
    exchange: str = "KUCOIN",
    base_timeframe: str = "15m",
    pattern_length: int = 3,
    min_size_increase: float = 10.0,
    limit: int = 15,
) -> dict:
    """Advanced candle pattern analysis using multi-timeframe data.

    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        base_timeframe: Base timeframe for analysis (5m, 15m, 1h, 4h)
        pattern_length: Number of consecutive periods to analyse (2-4)
        min_size_increase: Minimum percentage increase in candle size
        limit: Maximum number of results to return
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    base_timeframe = sanitize_timeframe(base_timeframe, "15m")
    pattern_length = max(2, min(4, pattern_length))
    min_size_increase = max(5.0, min(50.0, min_size_increase))
    limit = max(1, min(30, limit))

    symbols = load_symbols(exchange)
    if not symbols:
        return {"error": f"No symbols found for exchange: {exchange}", "exchange": exchange}
    symbols = symbols[: min(limit * 2, 100)]

    if TRADINGVIEW_SCREENER_AVAILABLE:
        try:
            results = fetch_multi_timeframe_patterns(exchange, symbols, base_timeframe, pattern_length, min_size_increase)
            return {
                "exchange": exchange,
                "base_timeframe": base_timeframe,
                "pattern_length": pattern_length,
                "min_size_increase": min_size_increase,
                "method": "multi-timeframe",
                "total_found": len(results),
                "data": results[:limit],
            }
        except Exception:
            pass  # Fall through to single-timeframe fallback

    return scan_advanced_candle_patterns_single_tf(exchange, symbols, base_timeframe, pattern_length, min_size_increase, limit)


# ── Volume scanner tools ───────────────────────────────────────────────────────

@mcp.tool()
def volume_breakout_scanner(
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    volume_multiplier: float = 2.0,
    price_change_min: float = 3.0,
    limit: int = 25,
) -> list[dict] | dict:
    """Detect coins with volume breakout + price breakout.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, MEXC, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        volume_multiplier: How many times the volume should be above normal level (default 2.0)
        price_change_min: Minimum price change percentage (default 3.0)
        limit: Number of rows to return (max 50)

    Returns ``list[dict]`` on success, or an error envelope on total upstream
    failure (``{"error": {"code": "ALL_BATCHES_FAILED", ...}}``). The empty
    list now strictly means "no matches today"; rate-limit cliffs surface
    explicitly.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    volume_multiplier = max(1.5, min(10.0, volume_multiplier))
    price_change_min = max(1.0, min(20.0, price_change_min))
    limit = max(1, min(limit, 50))
    try:
        return volume_breakout_scan(exchange, timeframe, volume_multiplier, price_change_min, limit)
    except BatchExecutionError as e:
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(e),
            batches_attempted=e.batches_attempted,
            batches_failed=e.batches_failed,
            first_error=e.first_error,
        )


@mcp.tool()
def volume_confirmation_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Detailed volume confirmation analysis for a specific coin.

    Args:
        symbol: Coin symbol (e.g., BTCUSDT)
        exchange: Exchange name
        timeframe: Time frame for analysis
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    return volume_confirmation_analyze(symbol, exchange, timeframe)


@mcp.tool()
def smart_volume_scanner(
    exchange: str = "KUCOIN",
    min_volume_ratio: float = 2.0,
    min_price_change: float = 2.0,
    rsi_range: str = "any",
    limit: int = 20,
) -> list[dict] | dict:
    """Smart volume + technical analysis combination scanner.

    Args:
        exchange: Exchange name
        min_volume_ratio: Minimum volume multiplier (default 2.0)
        min_price_change: Minimum price change percentage (default 2.0)
        rsi_range: "oversold" (<30), "overbought" (>70), "neutral" (30-70), "any"
        limit: Number of results (max 30)

    Returns ``list[dict]`` on success, or an error envelope on total upstream
    failure (``{"error": {"code": "ALL_BATCHES_FAILED", ...}}``) — inherited
    from the inner ``volume_breakout_scan`` call.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    min_volume_ratio = max(1.2, min(10.0, min_volume_ratio))
    min_price_change = max(0.5, min(20.0, min_price_change))
    limit = max(1, min(limit, 30))
    try:
        return smart_volume_scan(exchange, min_volume_ratio, min_price_change, rsi_range, limit)
    except BatchExecutionError as e:
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(e),
            batches_attempted=e.batches_attempted,
            batches_failed=e.batches_failed,
            first_error=e.first_error,
        )


# ── Multi-agent analysis ───────────────────────────────────────────────────────

@mcp.tool()
def multi_agent_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Run a multi-agent debate (Technical, Sentiment, Risk) for a specific symbol.

    Args:
        symbol: Symbol — crypto: "BTCUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX), "GDX" (AMEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, AMEX, NYSEARCA, PCX, SSE, SZSE, TWSE, TPEX
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W)

    Returns:
        A structured debate between 3 AI agents culminating in a final trading decision.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    full_symbol = normalize_tradingview_symbol(symbol, exchange)
    return run_multi_agent_analysis(full_symbol, exchange, timeframe)


# ── EGX market tools ───────────────────────────────────────────────────────────

@mcp.tool()
def egx_market_overview(timeframe: str = "1D", limit: int = 10) -> dict:
    """Get a comprehensive overview of the Egyptian Exchange (EGX) market.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D for stocks)
        limit: Number of stocks per category (max 20)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 20))
    return get_egx_market_overview(timeframe, limit)


@mcp.tool()
def egx_sector_scan(sector: str = "", timeframe: str = "1D", limit: int = 20) -> dict:
    """Scan EGX stocks by sector. Shows available sectors if none specified.

    Args:
        sector: Sector name (banks, healthcare_and_pharma, real_estate, etc.)
                Leave empty to list all sectors.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Max results per sector (max 50)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 50))
    return scan_egx_sector(sector, timeframe, limit)


@mcp.tool()
def egx_sector_scanner(
    timeframe: str = "1D",
    top_n_sectors: int = 5,
    top_n_stocks: int = 3,
    min_stock_score: int = 60,
) -> dict:
    """Sector rotation scanner for EGX — identifies hot/cold sectors and top picks.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        top_n_sectors: Number of top sectors to show stock picks for (1-18, default 5)
        top_n_stocks: Number of top stocks per highlighted sector (1-10, default 3)
        min_stock_score: Minimum stock score for picks (0-100, default 60)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    top_n_sectors = max(1, min(18, top_n_sectors))
    top_n_stocks = max(1, min(10, top_n_stocks))
    min_stock_score = max(0, min(100, min_stock_score))
    return run_egx_sector_scanner(timeframe, top_n_sectors, top_n_stocks, min_stock_score)


@mcp.tool()
def egx_index_analysis(index: str = "EGX30", timeframe: str = "1D", limit: int = 30) -> dict:
    """Analyse an EGX index showing constituent performance with full indicators.

    Args:
        index: EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        limit: Number of stocks to show in detail (max 100)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 100))
    return analyze_egx_index(index, timeframe, limit)


@mcp.tool()
def egx_stock_screener(
    timeframe: str = "1D",
    min_score: int = 55,
    index_filter: str = "",
    limit: int = 20,
) -> dict:
    """Production stock ranking engine for EGX — finds strong stocks with actionable setups.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        min_score: Minimum stock score to include (0-100, default 55)
        index_filter: Filter by index — EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ
        limit: Number of results (max 50)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    min_score = max(0, min(100, min_score))
    limit = max(1, min(50, limit))
    return screen_egx_stocks(timeframe, min_score, index_filter, limit)


@mcp.tool()
def egx_trade_plan(symbol: str, timeframe: str = "1D") -> dict:
    """Generate a full trade plan for a specific EGX stock.

    Args:
        symbol: EGX stock symbol (e.g., "COMI", "TMGH", "FWRY")
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    return generate_egx_trade_plan(symbol, timeframe)


@mcp.tool()
def egx_fibonacci_retracement(symbol: str, lookback: str = "52W", timeframe: str = "1D") -> dict:
    """Fibonacci retracement analysis for EGX stocks.

    Args:
        symbol: EGX stock symbol (e.g., "COMI", "TMGH", "FWRY")
        lookback: Period for swing high/low — "1M", "3M", "6M", "52W", "ALL" (default 52W)
        timeframe: Analysis timeframe (5m, 15m, 1h, 4h, 1D, 1W, 1M — default 1D)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    lookback = lookback.strip().upper()
    return analyze_egx_fibonacci(symbol, lookback, timeframe)


# ── Multi-timeframe analysis ───────────────────────────────────────────────────

@mcp.tool()
def multi_timeframe_analysis(symbol: str, exchange: str = "KUCOIN") -> dict:
    """Multi-timeframe alignment analysis (Weekly → Daily → 4H → 1H → 15m).

    Args:
        symbol: Symbol — crypto: "BTCUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX), "GDX" (AMEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, AMEX, NYSEARCA, PCX, SSE, SZSE, TWSE, TPEX
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    full_symbol = normalize_tradingview_symbol(symbol, exchange)
    return run_multi_timeframe_analysis(full_symbol, exchange)


# ── Sentiment & news tools ─────────────────────────────────────────────────────

@mcp.tool()
def market_sentiment(symbol: str, category: str = "all", limit: int = 20) -> dict:
    """Real-time sentiment analysis for stocks and crypto.

    For IDX/Indonesian stocks (category="indonesia"), uses Telegram CIA groups as primary source.
    For US stocks and crypto, uses Reddit.

    Args:
        symbol:   Asset symbol ("AAPL", "BTC", "ETH", "TSLA", "BBCA", "GOTO")
        category: "crypto" | "stocks" | "all" | "indonesia" (IDX → Telegram sentiment)
        limit:    Number of posts/messages to analyse
    """
    if category == "indonesia":
        # Try local knowledge base first (fast, no network)
        tg_kb = _tg_query_kb(ticker=symbol, days_back=7, limit=limit)
        if tg_kb.get("count", 0) > 0:
            ss   = tg_kb.get("sentiment_summary", {})
            msgs = tg_kb.get("messages", [])
            newest_date = msgs[0]["date"][:10]  if msgs else "?"
            oldest_date = msgs[-1]["date"][:10] if msgs else "?"
            return {
                "success":         True,
                "symbol":          symbol,
                "source":          "Telegram CIA groups (knowledge base)",
                "posts_analyzed":  tg_kb["count"],
                "sentiment_label": ss.get("overall", "Neutral"),
                "sentiment_score": round((ss.get("bull_pct", 0) - ss.get("bear_pct", 0)) / 100, 3),
                "data_from":       oldest_date,
                "data_to":         newest_date,
                "days_back":       7,
                "details":         tg_kb,
            }
        # Fallback: live fetch dari CIA saham folder
        tg_live = _tg_read_folder(
            "CIA saham", ticker_filter=symbol, hours_back=168,
            limit_per_chat=limit, save_to_db=True
        )
        if tg_live.get("success"):
            cs    = tg_live.get("combined_sentiment", {})
            total = cs.get("total", 1) or 1
            live_msgs   = tg_live.get("messages", [])
            newest_date = live_msgs[0]["date"][:10]  if live_msgs else "?"
            oldest_date = live_msgs[-1]["date"][:10] if live_msgs else "?"
            return {
                "success":         True,
                "symbol":          symbol,
                "source":          "Telegram CIA saham (live)",
                "posts_analyzed":  total,
                "sentiment_label": cs.get("label", "Neutral"),
                "sentiment_score": round((cs.get("bullish", 0) - cs.get("bearish", 0)) / total, 3),
                "data_from":       oldest_date,
                "data_to":         newest_date,
                "details":         tg_live,
            }
        return {"success": False, "symbol": symbol, "error": "Tidak ada data Telegram untuk ticker ini"}
    return analyze_sentiment(symbol, category, limit)


@mcp.tool()
def financial_news(symbol: str = None, category: str = "stocks", limit: int = 10) -> dict:
    """Real-time financial news from RSS feeds.

    Args:
        symbol: Optional ticker filter. For IDX stocks use ticker only e.g. "BBCA", "TPIA".
                For US stocks: "AAPL", "TSLA". None = all news from category.
        category: Feed category:
                  - "indonesia" → IDX/BEI news: Kontan, CNBC Indonesia, IDX Channel,
                    Katadata, Emiten News, Detik Finance, Bisnis.com (scraper)
                  - "stocks"    → Global: Yahoo Finance, MarketWatch, CNBC
                  - "crypto"    → CoinDesk, CoinTelegraph
                  - "all"       → Global stocks + crypto combined
        limit: Max number of news items (default 10)
    """
    return fetch_news_summary(symbol, category, limit)


@mcp.tool()
def combined_analysis(symbol: str, exchange: str = "NASDAQ", timeframe: str = "1D") -> dict:
    """POWER TOOL: TradingView technical analysis + Telegram sentiment (IDX) / Reddit sentiment (global) + Financial news.

    For IDX/BEI stocks, sentiment is sourced from Telegram CIA groups (knowledge base or live fetch).
    For US stocks and crypto, sentiment is sourced from Reddit.

    Args:
        symbol:   Asset symbol ("AAPL", "BTCUSDT", "THYAO", "GDX", "BBCA", "GOTO")
        exchange: Exchange (NASDAQ, NYSE, AMEX, NYSEARCA, PCX, BINANCE, KUCOIN, MEXC, BIST, EGX, IDX, TWSE, TPEX)
        timeframe: Analysis timeframe (5m, 15m, 1h, 4h, 1D, 1W)
    """
    tech = coin_analysis(symbol, exchange, timeframe)
    _exc = exchange.upper()

    if _exc in ["BINANCE", "KUCOIN", "BYBIT", "MEXC"]:
        cat = "crypto"
        use_telegram = False
    elif _exc in ["IDX", "BEI", "IDX:*"]:
        cat = "indonesia"
        use_telegram = True
    else:
        cat = "stocks"
        use_telegram = False

    news = fetch_news_summary(symbol, category=cat, limit=5)

    # ── Sentiment source routing ──────────────────────────────────────────────
    if use_telegram:
        # 1. Try local knowledge base first (cepat, no network)
        tg_kb = _tg_query_kb(ticker=symbol, days_back=7)
        if tg_kb.get("count", 0) > 0:
            ss    = tg_kb.get("sentiment_summary", {})
            bull_pct = ss.get("bull_pct", 0)
            bear_pct = ss.get("bear_pct", 0)
            msgs  = tg_kb.get("messages", [])
            # Extract date range from messages (sorted DESC by date)
            newest_date = msgs[0]["date"][:10]  if msgs else "?"
            oldest_date = msgs[-1]["date"][:10] if msgs else "?"
            sentiment = {
                "sentiment_score":  round((bull_pct - bear_pct) / 100, 3),
                "sentiment_label":  ss.get("overall", "Neutral"),
                "posts_analyzed":   tg_kb["count"],
                "source":           "Telegram CIA (knowledge base)",
                "data_from":        oldest_date,
                "data_to":          newest_date,
                "days_back":        7,
            }
        else:
            # 2. Live fetch dari CIA saham folder
            tg_live = _tg_read_folder(
                "CIA saham", ticker_filter=symbol,
                hours_back=168, limit_per_chat=50, save_to_db=True
            )
            if tg_live.get("success") and tg_live.get("total_messages", 0) > 0:
                cs    = tg_live.get("combined_sentiment", {})
                total = cs.get("total", 1) or 1
                live_msgs = tg_live.get("messages", [])
                newest_date = live_msgs[0]["date"][:10]  if live_msgs else "?"
                oldest_date = live_msgs[-1]["date"][:10] if live_msgs else "?"
                sentiment = {
                    "sentiment_score":  round((cs.get("bullish", 0) - cs.get("bearish", 0)) / total, 3),
                    "sentiment_label":  cs.get("label", "Neutral"),
                    "posts_analyzed":   total,
                    "source":           "Telegram CIA saham (live)",
                    "data_from":        oldest_date,
                    "data_to":          newest_date,
                    "days_back":        7,
                }
            else:
                sentiment = {
                    "sentiment_score": 0,
                    "sentiment_label": "No Data",
                    "posts_analyzed":  0,
                    "source":          "Telegram (tidak ada data untuk ticker ini)",
                    "data_from":       None,
                    "data_to":         None,
                }
    else:
        sentiment = analyze_sentiment(symbol, category=cat)
        sentiment["source"] = "Reddit"

    # ── Confluence ────────────────────────────────────────────────────────────
    tech_momentum = tech.get("market_sentiment", {}).get("momentum", "") if isinstance(tech, dict) else ""
    tech_bullish  = tech_momentum == "Bullish"
    sent_bullish  = sentiment.get("sentiment_score", 0) > 0.1
    signals_agree = tech_bullish == sent_bullish
    confidence    = "HIGH" if signals_agree else "MIXED"
    tech_signal   = tech.get("market_sentiment", {}).get("buy_sell_signal", "N/A") if isinstance(tech, dict) else "N/A"
    src           = sentiment.get("source", "sentiment")

    return {
        "symbol":    symbol,
        "exchange":  exchange,
        "timeframe": timeframe,
        "technical": tech,
        "sentiment": sentiment,
        "news":      {"count": news.get("count", 0), "latest": news.get("items", [])[:3]},
        "confluence": {
            "signals_agree": signals_agree,
            "confidence":    confidence,
            "recommendation": (
                f"Technical {tech_signal} "
                f"{'confirmed by' if signals_agree else 'conflicts with'} "
                f"{sentiment.get('sentiment_label', 'Neutral')} {src} sentiment "
                f"({sentiment.get('posts_analyzed', 0)} messages, "
                f"data {sentiment.get('data_from', '?')} → {sentiment.get('data_to', '?')})"
            ),
        },
    }


# ── Backtest tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def backtest_strategy(
    symbol: str,
    strategy: str,
    period: str = "1y",
    initial_capital: float = 10000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    interval: str = "1d",
    include_trade_log: bool = False,
    include_equity_curve: bool = False,
) -> dict:
    """Backtest a trading strategy on historical data with institutional-grade metrics.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, THYAO.IS, ^GSPC)
        strategy: rsi | bollinger | macd | ema_cross | supertrend | donchian
                  | rsi_pullback | keltner_breakout | triple_ema
                  (rsi_pullback and triple_ema need period >= '1y' for SMA200 warmup)
        period: '1mo', '3mo', '6mo', '1y', '2y'
        initial_capital: Starting capital in USD (default $10,000)
        commission_pct: Per-trade commission % (default 0.1%)
        slippage_pct: Per-trade slippage % (default 0.05%)
        interval: '1d' (daily) or '1h' (hourly)
        include_trade_log: Include full per-trade log (default False)
        include_equity_curve: Include equity curve data points (default False)
    """
    return run_backtest(
        symbol, strategy, period, initial_capital,
        commission_pct, slippage_pct, interval,
        include_trade_log, include_equity_curve,
    )


@mcp.tool()
def compare_strategies(
    symbol: str,
    period: str = "1y",
    initial_capital: float = 10000.0,
    interval: str = "1d",
) -> dict:
    """Run all 9 strategies (RSI, Bollinger, MACD, EMA Cross, Supertrend, Donchian, RSI Pullback, Keltner Breakout, Triple EMA) and return a ranked leaderboard.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, SPY…)
        period: '1mo', '3mo', '6mo', '1y', '2y'
                (period >= '1y' recommended so rsi_pullback and triple_ema can
                 complete SMA200 warmup; otherwise they contribute zero trades)
        initial_capital: Starting capital in USD (default $10,000)
        interval: '1d' (daily) or '1h' (hourly)
    """
    return _compare_strategies(symbol, period, initial_capital, interval=interval)


@mcp.tool()
def walk_forward_backtest_strategy(
    symbol: str,
    strategy: str,
    period: str = "2y",
    initial_capital: float = 10000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    n_splits: int = 3,
    train_ratio: float = 0.7,
    interval: str = "1d",
) -> dict:
    """Walk-forward backtest to detect overfitting — validates strategy on unseen data.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, SPY…)
        strategy: rsi | bollinger | macd | ema_cross | supertrend | donchian
                  | keltner_breakout
                  (rsi_pullback and triple_ema not supported here — SMA200 warmup
                   exceeds typical fold size; use run_backtest with period='2y')
        period: '1mo', '3mo', '6mo', '1y', '2y' (recommend '2y')
        initial_capital: Starting capital per fold in USD (default $10,000)
        commission_pct: Per-trade commission % (default 0.1%)
        slippage_pct: Per-trade slippage % (default 0.05%)
        n_splits: Number of walk-forward folds (default 3, max 10)
        train_ratio: Fraction of each fold used for training (default 0.7)
        interval: '1d' (daily) or '1h' (hourly)
    """
    return walk_forward_backtest(
        symbol, strategy, period, initial_capital,
        commission_pct, slippage_pct, n_splits, train_ratio, interval,
    )


@mcp.tool()
def backtest_cia_strategy(
    symbol: str,
    strategy: str = "cia_ketat",
    period: str = "1y",
    initial_capital: float = 10_000_000.0,
    commission_buy_pct: float = 0.15,
    commission_sell_pct: float = 0.25,
    slippage_pct: float = 0.05,
    tight_pct: float = 5.0,
    kamehameha_ratio: float = 2.5,
    ara_guard: bool = True,
    ara_arb_simulation: bool = True,
    include_trade_log: bool = False,
    include_equity_curve: bool = False,
) -> dict:
    """Backtest satu CIA trading setup pada saham IDX.

    Mensimulasikan trading CIA style dengan aturan real IDX:
      - ARA guard: tidak entry kalau candle sudah kena auto-rejection +20%
      - ARB simulation: force exit kalau harga kena floor -20%
      - Komisi IDX: buy (0.15%) + sell (0.25%) terpisah (bukan flat %)

    Args:
        symbol:              Kode saham IDX, contoh: "BBCA", "TLKM", "GOTO"
                             (auto-append .JK untuk Yahoo Finance)
        strategy:            cia_superketat | cia_ketat | cia_kamehameha |
                             cia_rainbow | cia_star | cia_sunflower
        period:              1mo | 3mo | 6mo | 1y | 2y
        initial_capital:     Modal awal dalam IDR (default 10 juta)
        commission_buy_pct:  Komisi beli % (default 0.15%)
        commission_sell_pct: Komisi jual % (default 0.25%)
        slippage_pct:        Slippage per sisi % (default 0.05%)
        tight_pct:           Batas jarak % ke MA untuk kondisi "ketat" (default 5%)
        kamehameha_ratio:    Min volume vs V60 untuk Kamehameha (default 2.5×)
        ara_guard:           Skip entry di hari ARA (default True)
        ara_arb_simulation:  Force exit di level ARB kalau kena (default True)
        include_trade_log:   Sertakan log per trade lengkap
        include_equity_curve: Sertakan data equity curve
    """
    return _run_cia_backtest(
        symbol=symbol,
        strategy=strategy,
        period=period,
        initial_capital=initial_capital,
        commission_buy_pct=commission_buy_pct,
        commission_sell_pct=commission_sell_pct,
        slippage_pct=slippage_pct,
        tight_pct=tight_pct,
        kamehameha_ratio=kamehameha_ratio,
        ara_guard=ara_guard,
        ara_arb_simulation=ara_arb_simulation,
        include_trade_log=include_trade_log,
        include_equity_curve=include_equity_curve,
    )


@mcp.tool()
def compare_cia_strategies(
    symbol: str,
    period: str = "1y",
    initial_capital: float = 10_000_000.0,
    commission_buy_pct: float = 0.15,
    commission_sell_pct: float = 0.25,
    slippage_pct: float = 0.05,
    tight_pct: float = 5.0,
    kamehameha_ratio: float = 2.5,
    ara_guard: bool = True,
    ara_arb_simulation: bool = True,
) -> dict:
    """Jalankan semua 6 strategi CIA pada satu saham IDX dan ranking berdasarkan performa.

    Berguna untuk mengetahui setup CIA mana yang paling efektif untuk saham tertentu.
    Hasilnya diurutkan dari total return tertinggi.

    CIA setups yang dibandingkan:
      cia_superketat  — close > MA5/10/20 semua dalam 5% (AND condition)
      cia_ketat       — close > MA5/10/20, minimal satu dalam 5% (OR condition)
      cia_kamehameha  — volume > 2.5× V60 dan close > MA20
      cia_rainbow     — close di atas semua MA (5/10/20/50/100/200)
      cia_star        — Ketat + Kamehameha bersamaan (setup premium)
      cia_sunflower   — Ketat pertama setelah gap up

    Args:
        symbol:              Kode saham IDX, contoh: "BBCA", "TLKM"
        period:              1mo | 3mo | 6mo | 1y | 2y
        initial_capital:     Modal awal dalam IDR (default 10 juta)
        commission_buy_pct:  Komisi beli % (default 0.15%)
        commission_sell_pct: Komisi jual % (default 0.25%)
        slippage_pct:        Slippage per sisi % (default 0.05%)
        tight_pct:           Batas jarak % ke MA (default 5%)
        kamehameha_ratio:    Volume multiplier vs V60 (default 2.5×)
        ara_guard:           Skip entry di hari ARA (default True)
        ara_arb_simulation:  Simulasi ARB force exit (default True)
    """
    return _compare_cia_strategies(
        symbol=symbol,
        period=period,
        initial_capital=initial_capital,
        commission_buy_pct=commission_buy_pct,
        commission_sell_pct=commission_sell_pct,
        slippage_pct=slippage_pct,
        tight_pct=tight_pct,
        kamehameha_ratio=kamehameha_ratio,
        ara_guard=ara_guard,
        ara_arb_simulation=ara_arb_simulation,
    )


# ── Yahoo Finance tools ────────────────────────────────────────────────────────

@mcp.tool()
def yahoo_price(symbol: str) -> dict:
    """Real-time price quote from Yahoo Finance for any stock, crypto, ETF or index.

    Args:
        symbol: Yahoo Finance symbol — e.g. AAPL, BTC-USD, SPY, ^GSPC, EURUSD=X, THYAO.IS
    """
    return get_price(normalize_yahoo_symbol(symbol))


@mcp.tool()
def market_snapshot() -> dict:
    """Global market overview: major indices, top crypto, FX rates, and key ETFs.
    Powered by Yahoo Finance.
    """
    return get_market_snapshot()


@mcp.tool()
def bitcoin_market_pulse() -> dict:
    """Single-call BTC macro context: price, dominance, total market cap + risk assessment.

    Use this WHENEVER analyzing any cryptocurrency (altcoin or BTC itself) to
    get the broader market frame in one shot. A SOL/ETH/whatever setup looks
    very different when BTC is dumping with rising dominance vs. when alts
    are leading. Calling this once gives Claude the macro context to provide
    Bitcoin-aware commentary alongside the per-coin analysis - without
    chaining 2-3 separate yahoo_price + manual reasoning calls.

    Returns:
      - bitcoin: price, 24h change %, volume, market cap
      - dominance: BTC and ETH market-cap share of total crypto
      - total_market: total crypto mcap + 24h change + active coin count
      - assessment: label (HIGH_RISK / ALT_RISK / ALT_FAVORABLE / OPPORTUNITY_WITH_CAUTION / NEUTRAL) + 1-paragraph reasoning
    """
    return get_bitcoin_market_pulse()


@mcp.tool()
def stock_extended_hours(symbol: str) -> dict:
    """Real-time pre-market and after-hours prices for a US stock symbol.

    Use this when the user asks about a stock outside the regular 9:30am-4pm
    ET session — earnings reactions, overnight news, "what is X doing in
    after-hours?", "how did Y open in pre-market?". Returns the most recent
    valid print from each session window (pre-market, regular, post-market)
    along with computed % changes vs. the previous close and the regular
    close, respectively.

    During the regular session, post_market will be null (no data yet).
    On weekends/holidays, returns whatever's most recent in each window.

    Args:
        symbol: US stock symbol — AAPL, NVDA, TSLA, SPY, ^GSPC, etc.

    Returns:
        - pre_market: {price, as_of_utc, change_vs_previous_close_pct} or null
        - regular: {price, as_of_utc, change_pct} (consolidated tape close)
        - post_market: {price, as_of_utc, change_vs_regular_close_pct} or null
        - previous_close, currency, exchange, market_state for context
    """
    return get_extended_hours_price(symbol)


@mcp.tool()
def stock_options_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    """Full options chain (calls + puts) for a US stock symbol and one expiry.

    Use this when the user asks "what's the options chain for X?", "show me
    AAPL puts expiring next Friday", or wants to inspect bid/ask/IV/volume on
    a specific strike. If no expiry is provided, returns the nearest expiry
    so Claude can quote it back and ask "want a different one?".

    Args:
        symbol: US stock symbol — AAPL, NVDA, TSLA, SPY, etc.
        expiry: Optional ISO date (YYYY-MM-DD). Must match one of the
            `available_expiries` Yahoo returns; otherwise returns an error
            with the list of valid dates.

    Returns:
        - underlying_price, underlying_change_pct
        - requested_expiry, available_expiries (list of YYYY-MM-DD)
        - call_count, put_count
        - calls: list of {strike, last_price, bid, ask, volume,
          open_interest, implied_volatility, in_the_money, expiration}
        - puts: same shape as calls
    """
    return get_options_chain(symbol, expiry)


@mcp.tool()
def stock_options_unusual_activity(
    symbol: str,
    top_n: int = 10,
    min_volume: int = 100,
    expiries: int = 4,
) -> dict:
    """Top strikes by volume / open-interest ratio — institutional positioning signal.

    Use this when the user asks "any unusual options activity on X?", "where
    is the smart money positioned on NVDA before earnings?", or wants a
    V/OI screener for a ticker. A V/OI ratio > 1 means today's volume already
    exceeds standing open interest, which classically flags fresh institutional
    positioning on a specific strike in a specific direction (call vs put).

    Scans the soonest few expirations, filters out illiquid strikes (under
    `min_volume`), and returns the top-N sorted by V/OI descending. Also
    returns aggregate call vs put volume so Claude can comment on the
    overall directional bias.

    Args:
        symbol: US stock symbol — AAPL, NVDA, TSLA, SPY, META, etc.
        top_n: How many strikes to return. Default 10.
        min_volume: Filter floor for today's volume — prevents noise from
            illiquid strikes with high V/OI ratios. Default 100.
        expiries: Number of soonest expirations to scan. Default 4
            (typically covers ~1 month of weeklies + monthlies).

    Returns:
        - underlying_price
        - expiries_scanned (list of YYYY-MM-DD)
        - total_call_volume, total_put_volume, put_call_volume_ratio
        - unusual: list of top-N contracts sorted by V/OI desc, each with
          {strike, side (call|put), expiration, volume, open_interest,
          v_oi_ratio, last_price, implied_volatility, in_the_money,
          strike_vs_spot_pct (moneyness)}
    """
    return get_unusual_options_activity(symbol, top_n, min_volume, expiries)


# ── Futures tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def futures_market_overview(
    category: str = "all",
    exchanges: str = "us",
    limit: int = 30,
    volume_min: int = 0,
) -> dict:
    """Top futures contracts sorted by trading volume.

    Args:
        category:   all | equity_index | energy | metals | agriculture | rates | forex | crypto_futures
        exchanges:  us (CME, COMEX, NYMEX, CBOT) | global (adds ICE, EUREX)
        limit:      max contracts to return (default 30)
        volume_min: minimum volume filter (0 = no filter)

    Returns:
        Dict with total_available count and list of contracts with OHLCV + % change.
    """
    try:
        return get_futures_overview(
            category=category,
            exchanges=exchanges,
            limit=limit,
            volume_min=volume_min,
        )
    except Exception as exc:
        return make_error(ErrorCode.SERVICE_ERROR, f"Futures overview failed: {exc}")


@mcp.tool()
def futures_top_movers(
    direction: str = "gainers",
    exchanges: str = "us",
    limit: int = 20,
    volume_min: int = 10,
) -> dict:
    """Futures contracts with the biggest percentage moves today.

    Args:
        direction:  gainers | losers
        exchanges:  us | global
        limit:      max results
        volume_min: minimum volume filter (default 10, filters illiquid contracts)

    Returns:
        List of futures ranked by % change with OHLCV data.
    """
    direction = direction.lower()
    if direction not in ("gainers", "losers"):
        direction = "gainers"
    try:
        return get_futures_movers(
            direction=direction,
            exchanges=exchanges,
            limit=limit,
            volume_min=volume_min,
        )
    except Exception as exc:
        return make_error(ErrorCode.SERVICE_ERROR, f"Futures movers failed: {exc}")


@mcp.tool()
def futures_category_snapshot(category: str = "energy") -> dict:
    """Quote all major front-month contracts in a specific futures category.

    Args:
        category: equity_index | energy | metals | agriculture | rates | forex | crypto_futures

    Returns:
        OHLCV quotes for the standard watchlist of contracts in that category.
        Example symbols: ES1! NQ1! (equity_index), CL1! NG1! (energy), GC1! SI1! (metals).
    """
    return get_futures_category_snapshot(category)


@mcp.tool()
def futures_watchlist() -> dict:
    """Return the full categorized list of well-known front-month futures symbols.

    Categories: equity_index, energy, metals, agriculture, rates, forex, crypto_futures.
    Use these symbols with futures_category_snapshot or coin_analysis for deeper analysis.
    """
    return get_futures_watchlist()


# ── IDX Technical Screener & Index Analysis ───────────────────────────────────

@mcp.tool()
def idx_stock_screener(
    timeframe:    str = "1D",
    min_score:    int = 55,
    index_filter: str = "",
    limit:        int = 20,
) -> dict:
    """Production stock ranking engine untuk IDX — temukan saham terbaik hari ini.

    Scan semua saham IDX, score tiap saham (0-100), dan tampilkan:
    - qualified_trades: saham dengan setup actionable (score ≥ 70 + TQ ≥ 65)
    - watchlist: saham menarik tapi setup belum optimal
    - grade_distribution: penyebaran grade di universe yang discan

    Args:
        timeframe:    Interval analisis — 1D (default), 1W, 4H, 1H
        min_score:    Minimum stock score 0-100 (default 55)
        index_filter: Filter ke index tertentu — LQ45, IDX30, IDX80, KOMPAS100,
                      JII, IDXHIDIV20, IDXBUMN20 (kosong = semua IDX)
        limit:        Jumlah hasil maksimal (max 50, default 20)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    min_score = max(0, min(100, min_score))
    limit     = max(1, min(50, limit))
    return screen_idx_stocks(timeframe, min_score, index_filter, limit)


@mcp.tool()
def idx_top_gainers_losers(
    mode:           str   = "gainers",
    timeframe:      str   = "1D",
    limit:          int   = 30,
    min_change_pct: float = 0.0,
    min_volume_idr: float = 0.0,
    index_filter:   str   = "",
) -> dict:
    """Top gainers atau losers seluruh IDX berdasarkan % perubahan harga.

    Scan ~800 saham IDX (atau index tertentu), filter, dan sort by % change.
    Lebih cepat dari idx_stock_screener karena tidak melakukan scoring.
    Cocok untuk mencari saham yang ARA/bergerak kuat hari ini.

    Args:
        mode:           "gainers" (naik terbesar) | "losers" (turun terbesar)
        timeframe:      Interval — 1D (default), 4H, 1H, 1W
        limit:          Jumlah hasil (max 100, default 30)
        min_change_pct: Filter minimum % change (mis: 2.0 = hanya ≥2% naik)
        min_volume_idr: Filter minimum nilai transaksi jutaan IDR/hari
                        (mis: 500 = min 500 juta IDR; 0 = tidak difilter)
        index_filter:   Batasi ke index — LQ45, IDX30, IDX80, KOMPAS100,
                        JII, IDXHIDIV20, IDXBUMN20 (kosong = semua IDX)

    Returns:
        dict dengan results berisi: ticker, price, change_pct, volume_idr (juta),
        rsi, ma_pos (posisi vs EMA20/50/200), sector
    """
    timeframe      = sanitize_timeframe(timeframe, "1D")
    limit          = max(1, min(100, limit))
    min_change_pct = max(0.0, min_change_pct)
    min_vol_idr    = min_volume_idr * 1_000_000  # convert dari juta IDR ke raw IDR
    mode           = mode.lower() if mode.lower() in ("gainers", "losers") else "gainers"
    return get_idx_top_gainers(
        timeframe      = timeframe,
        limit          = limit,
        min_change_pct = min_change_pct,
        min_volume_idr = min_vol_idr,
        mode           = mode,
        index_filter   = index_filter,
    )


@mcp.tool()
def idx_index_analysis(
    index:     str = "LQ45",
    timeframe: str = "1D",
    limit:     int = 45,
) -> dict:
    """Analisis performa konstituen sebuah IDX index — breadth, sektor, dan top movers.

    Menampilkan market breadth (advancing/declining), sentiment index,
    sector breakdown ranked by avg change, top 5 gainers, top 5 losers,
    dan detail semua saham dalam index.

    Args:
        index:     Index yang dianalisis — LQ45 (default), IDX30, IDX80, KOMPAS100,
                   JII, IDXHIDIV20, IDXBUMN20
        timeframe: Interval analisis — 1D (default), 1W, 4H, 1H
        limit:     Jumlah saham yang ditampilkan detail (max 100)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit     = max(1, min(100, limit))
    return analyze_idx_index(index.strip().upper(), timeframe, limit)


@mcp.tool()
def scan_by_signal(
    signal:        str = "golden_cross",
    timeframe:     str = "1D",
    index_filter:  str = "",
    limit:         int = 20,
) -> dict:
    """Scan saham IDX berdasarkan sinyal teknikal spesifik.

    Sinyal tersedia:
      Trend/EMA : golden_cross, death_cross, ema_stack_bullish, ema_stack_bearish,
                  above_ema20, below_ema20
      Momentum  : rsi_oversold (<35), rsi_overbought (>70), rsi_neutral (40-60),
                  macd_bullish, macd_bearish
      Volatility: bollinger_squeeze (BB width <10%, breakout incoming)
      Volume    : volume_spike (>2x rata-rata)
      Levels    : near_resistance, near_support (dalam 2% pivot)
      Rating    : tv_buy, tv_strong_buy, tv_sell

    Args:
        signal:       Nama sinyal (contoh: "golden_cross", "rsi_oversold")
        timeframe:    Timeframe — 1D (default), 1W, 4H, 1H, 15m
        index_filter: Filter ke index tertentu — LQ45, IDX30, IDX80, KOMPAS100,
                      JII, IDXHIDIV20, IDXBUMN20. Kosong = scan semua IDX.
        limit:        Maks hasil (default 20, max 50)

    Example:
        scan_by_signal("golden_cross", index_filter="LQ45")
        scan_by_signal("rsi_oversold", timeframe="1D")
        scan_by_signal("bollinger_squeeze", index_filter="IDX80")
        scan_by_signal("volume_spike")
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit     = max(1, min(50, limit))
    return _scan_by_signal(
        signal=signal,
        timeframe=timeframe,
        index_filter=index_filter,
        limit=limit,
    )


# ── CIA Setup Scanner ──────────────────────────────────────────────────────────

@mcp.tool()
def scan_cia_setups(
    setup_filter:     str   = "all",
    min_volume_idr:   float = 0.0,
    index_filter:     str   = "",
    limit:            int   = 50,
    timeframe:        str   = "1D",
    tight_pct:        float = 5.0,
    kamehameha_ratio: float = 2.5,
    min_above_ma20:   bool  = True,
) -> dict:
    """Scan seluruh IDX (~866 saham) untuk CIA-specific setups.

    Setup yang dideteksi:
      STAR ⭐        = Ketat/Superketat + Kamehameha — setup premium terkuat
      SUPERKETAT ⚡  = close > MA5/10/20 AND semua jarak ≤ tight_pct% (AND condition)
                       titik entry terbaik, CL ketat di bawah semua MA
      KETAT          = close > MA5/10/20 AND salah satu jarak ≤ tight_pct% (OR condition)
                       konfirmasi tren mulai berjalan
      KAMEHAMEHA 💥  = volume > kamehameha_ratio × avg_volume_10d
                       ledakan volume — bisa terjadi TANPA setup MA
      RAINBOW 🌈    = close > MA5/10/20/50/100/200 sekaligus, tidak ada resistance
      ABOVE_MA20     = close > MA20 (syarat minimal saat IHSG bearish)

    Args:
        setup_filter:     Filter: "all", "superketat", "ketat", "kamehameha",
                          "star", "rainbow", "above_ma20". Default "all".
        min_volume_idr:   Minimum nilai transaksi harian dalam MILIAR IDR.
                          Default 0 (no filter) — sama dengan CIAbot yang tidak filter
                          volume sama sekali. Set nilai positif untuk filter likuiditas.
        index_filter:     Filter ke index: LQ45, IDX30, IDX80, KOMPAS100, JII, dll.
                          Kosong = scan semua IDX (~866 saham).
        limit:            Maks hasil per kategori setup (max 100). Default 30.
        timeframe:        1D (default), 1W, 4H, 1H, 15m.
        tight_pct:        Threshold jarak % ke MA untuk "ketat". Default 5.0%.
        kamehameha_ratio: Threshold volume vs V60 untuk kamehameha. Default 2.5x
                          (sama dengan CIA original: volume > 2.5x rata-rata 60 hari).
        min_above_ma20:   Jika True, hanya tampilkan saham di atas MA20.
                          Default True (kondisi IHSG bearish sekarang).

    Returns:
        setups: dict berisi list saham per kategori CIA setup
        summary: jumlah saham per setup
        scan_info: parameter yang dipakai
        total_scanned, total_with_setup

    Example:
        scan_cia_setups()                              # semua setup, minimal 500jt IDR/hari
        scan_cia_setups("all", min_volume_idr=0)       # pure CIA, no vol filter (seperti CIAbot)
        scan_cia_setups("star")                        # hanya STAR setup
        scan_cia_setups("superketat", tight_pct=3.0)  # superketat sangat ketat ≤3%
        scan_cia_setups("kamehameha", kamehameha_ratio=3.0)   # volume > 3x avg
        scan_cia_setups("all", index_filter="LQ45")   # scan LQ45 saja
        scan_cia_setups("all", min_above_ma20=False)  # termasuk saham di bawah MA20
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    min_vol_raw = max(0.0, min_volume_idr) * 1_000_000_000  # konversi miliar ke IDR
    tight_pct   = max(0.5, min(20.0, tight_pct))
    kame_ratio  = max(1.1, min(10.0, kamehameha_ratio))
    limit       = max(1, min(100, limit))

    return _scan_cia_setups(
        setup_filter      = setup_filter,
        min_volume_idr    = min_vol_raw,
        index_filter      = index_filter,
        limit             = limit,
        timeframe         = timeframe,
        tight_pct         = tight_pct,
        kamehameha_ratio  = kame_ratio,
        min_above_ma20    = min_above_ma20,
    )


@mcp.tool()
def scan_sector_rotation(
    timeframe:      str   = "1D",
    tight_pct:      float = 5.0,
    min_volume_idr: float = 0.0,
) -> dict:
    """Scan kekuatan sektor IDX — tahu sektor mana yang sedang 'jalan' vs lemah.

    Untuk setiap sektor, hitung:
      - % saham di atas MA20 / MA50 / MA200
      - Jumlah saham ketat, superketat, rainbow
      - Health score = weighted average (MA20 50% + MA50 30% + MA200 20%)
      - Strength label: 🔥 KUAT / 📈 MODERAT / 📉 LEMAH / ❄️ SANGAT LEMAH

    Sektor diurutkan dari terkuat ke terlemah.

    Args:
        timeframe:      1D (default), 1W, 4H, 1H.
        tight_pct:      Threshold % jarak MA untuk ketat/superketat. Default 5%.
        min_volume_idr: Filter likuiditas dalam miliar IDR. Default 0 (no filter).

    Example:
        scan_sector_rotation()             # semua saham, daily
        scan_sector_rotation("1W")         # weekly — trend lebih besar
        scan_sector_rotation(min_volume_idr=0.5)  # saham ≥500jt IDR/hari saja
    """
    from tradingview_mcp.core.services.cia_scanner_service import (
        scan_sector_rotation as _scan_sector,
    )
    timeframe = sanitize_timeframe(timeframe, "1D")
    min_vol_raw = max(0.0, min_volume_idr) * 1_000_000_000
    return _scan_sector(
        timeframe=timeframe,
        tight_pct=max(0.5, min(20.0, tight_pct)),
        min_volume_idr=min_vol_raw,
    )


# ── Telegram Tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def telegram_list_chats(limit: int = 30) -> dict:
    """List semua grup/channel Telegram yang kamu ikuti — termasuk grup private.

    Berguna untuk menemukan 'identifier' (username atau ID numerik) dari tiap chat,
    yang dipakai sebagai parameter di telegram_read_messages dan telegram_stock_sentiment.

    Requires: session file (~/.mcp_atila_telegram.session) dari telegram_auth.py

    Args:
        limit: Jumlah chat yang ditampilkan (default 30)
    """
    return _tg_list_chats(limit=max(1, min(100, limit)))


@mcp.tool()
def telegram_read_messages(
    chat:       str,
    limit:      int = 50,
    keyword:    Optional[str] = None,
    hours_back: int = 24,
) -> dict:
    """Baca pesan terbaru dari grup/channel Telegram (termasuk grup private).

    Menggunakan akun Telegram kamu langsung (MTProto), bukan bot,
    sehingga bisa membaca semua grup/channel yang sudah kamu ikuti.

    Args:
        chat:       Username (@namachat) atau ID numerik grup/channel
        limit:      Jumlah pesan max (default 50)
        keyword:    Filter hanya pesan yang mengandung kata ini (optional)
        hours_back: Baca pesan N jam terakhir (default 24)

    Example:
        telegram_read_messages("@sahamindo", keyword="BBCA", hours_back=48)
        telegram_read_messages("-1001234567890", limit=100)
    """
    return _tg_read(chat=chat, limit=max(1, min(200, limit)),
                    keyword=keyword, hours_back=max(1, hours_back))


@mcp.tool()
def telegram_stock_sentiment(
    ticker:         str,
    chats:          Optional[list] = None,
    hours_back:     int = 48,
    limit_per_chat: int = 100,
) -> dict:
    """Scan sentimen saham IDX dari beberapa grup Telegram sekaligus.

    Mencari semua pesan yang menyebut ticker, lalu menganalisis sentimen
    (bullish/bearish) berdasarkan kata kunci bahasa Indonesia + Inggris.

    Args:
        ticker:         Kode saham IDX (contoh: "BBCA", "GOTO", "TLKM")
        chats:          List identifier grup/channel (username atau ID numerik).
                        Jika tidak diisi, otomatis pakai semua grup di knowledge base.
        hours_back:     Rentang waktu dalam jam (default 48)
        limit_per_chat: Max pesan per chat (default 100)

    Example:
        telegram_stock_sentiment("BBCA")
        telegram_stock_sentiment("BBCA", ["@sahamindo", "@forumidx", "-1001234567"])
        telegram_stock_sentiment("GOTO", ["@investasiidx"], hours_back=72)
    """
    return _tg_sentiment(
        ticker=ticker,
        chats=chats,
        hours_back=max(1, hours_back),
        limit_per_chat=max(10, min(500, limit_per_chat)),
    )


@mcp.tool()
def telegram_list_folders() -> dict:
    """List semua folder Telegram yang sudah dibuat — untuk cari nama folder yang bisa dipakai di telegram_read_folder."""
    return _tg_list_folders()


@mcp.tool()
def telegram_read_folder(
    folder_name:    str,
    limit_per_chat: int = 50,
    hours_back:     int = 24,
    ticker_filter:  Optional[str] = None,
    save_to_db:     bool = True,
) -> dict:
    """Baca semua grup dalam satu folder Telegram sekaligus — sentimen, top ticker, dan simpan ke knowledge base.

    Args:
        folder_name:    Nama folder Telegram (substring). Contoh: "CIA Member", "CIA saham", "CIA"
        limit_per_chat: Max pesan per grup (default 50, max 200)
        hours_back:     Baca pesan N jam terakhir (default 24)
        ticker_filter:  Filter hanya pesan yang menyebut saham ini (optional, contoh: "BBCA")
        save_to_db:     Simpan semua pesan ke knowledge base lokal (default True)

    Examples:
        telegram_read_folder("CIA Member")
        telegram_read_folder("CIA saham", ticker_filter="GOTO", hours_back=48)
        telegram_read_folder("CIA", hours_back=72, limit_per_chat=100)
    """
    return _tg_read_folder(
        folder_name=folder_name,
        limit_per_chat=max(10, min(200, limit_per_chat)),
        hours_back=max(1, hours_back),
        ticker_filter=ticker_filter,
        save_to_db=bool(save_to_db),
    )


@mcp.tool()
def telegram_query_knowledge(
    ticker:    Optional[str] = None,
    group:     Optional[str] = None,
    keyword:   Optional[str] = None,
    days_back: int = 7,
    limit:     int = 30,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
) -> dict:
    """Query knowledge base Telegram lokal — sentimen forum saham IDX dari grup yang sudah dibaca.

    Pesan dari grup Telegram (text, PDF, gambar) disimpan otomatis ke database lokal
    setiap kali telegram_read_messages dijalankan. Tool ini query database tanpa perlu
    koneksi Telegram aktif.

    Args:
        ticker:    Filter pesan yang menyebut saham ini (contoh: "BBCA", "GOTO")
        group:     Filter berdasarkan nama grup (substring)
        keyword:   Cari kata kunci dalam teks (contoh: "rights issue", "dividen", "bandar")
        days_back: Rentang hari ke belakang (default 7)
        limit:     Maks hasil (default 30)
        date_from: Filter pesan mulai tanggal ini (ISO: "2026-06-01"). Override days_back.
        date_to:   Filter pesan sampai tanggal ini (ISO: "2026-06-30").

    Examples:
        telegram_query_knowledge(ticker="BBCA") → semua diskusi BBCA dari forum
        telegram_query_knowledge(keyword="bandar", days_back=3)
        telegram_query_knowledge(ticker="GOTO", group="saham")
        telegram_query_knowledge(ticker="PKPK", date_from="2026-06-01", date_to="2026-06-15")
        telegram_query_knowledge(keyword="ARA", date_from="2026-06-29")
    """
    return _tg_query_kb(ticker=ticker, group=group, keyword=keyword,
                        days_back=days_back, limit=limit,
                        date_from=date_from, date_to=date_to)


@mcp.tool()
def telegram_knowledge_stats() -> dict:
    """Statistik knowledge base Telegram — berapa pesan tersimpan, dari grup apa, ticker apa yang paling banyak disebut.

    Berguna untuk melihat coverage knowledge base sebelum query sentimen.
    Tidak perlu koneksi Telegram aktif.
    """
    return _tg_kb_stats()


@mcp.tool()
def telegram_cia_alerts(
    days_back: int = 7,
    ticker: Optional[str] = None,
) -> dict:
    """Parse alert dari CIAbot IHSG Alert group jadi data terstruktur.
    Ekstrak ticker, CIA setup keywords, dan harga yang disebutkan.

    Query knowledge base lokal untuk pesan dari grup 'CIAbot IHSG Alert',
    lalu parsing setiap pesan untuk mendeteksi:
    - ticker IDX 4-huruf (regex)
    - CIA setup keywords: RAINBOW, KAMEHAMEHA, KAME, SUPERKETAT, KETAT, STAR, SUNFLOWER, ARA, ARB, BREAKOUT
    - harga IDX yang disebutkan (3-5 digit)

    Args:
        days_back: Ambil alert N hari ke belakang (default 7)
        ticker:    Filter hanya alert yang menyebut saham ini (optional, contoh: "PKPK")

    Examples:
        telegram_cia_alerts()
        telegram_cia_alerts(days_back=3, ticker="EMDE")
    """
    return _tg_cia_alerts(days_back=days_back, ticker=ticker)


@mcp.tool()
def telegram_semantic_search(
    query: str,
    n_results: int = 10,
    group_filter: str = None,
    sentiment_filter: str = None,
    days_back: int = 30,
) -> dict:
    """Cari pesan Telegram CIA secara semantik — temukan diskusi yang relevan meski kata-katanya beda.

    Berbeda dengan telegram_query_knowledge (exact keyword match), tool ini memahami makna/konteks.

    Contoh penggunaan:
        telegram_semantic_search("saham petrochemical prospek bagus")
        → temukan diskusi TPIA, BRPT meski tidak menyebut kata "petrochemical" persis

        telegram_semantic_search("bandar akumulasi diam-diam")
        → temukan pesan tentang accumulation patterns

        telegram_semantic_search("sektor perbankan outlook positif", sentiment_filter="bullish")
        → hanya pesan bullish tentang perbankan

        telegram_semantic_search("rights issue dilusi saham", days_back=7)
        → diskusi rights issue seminggu terakhir

    Args:
        query:            Pertanyaan atau topik bebas (Indonesia/Inggris)
        n_results:        Jumlah hasil yang dikembalikan (default 10)
        group_filter:     Filter nama grup CIA (substring, opsional). Contoh: "Diary", "Alert"
        sentiment_filter: Filter sentimen: "bullish", "bearish", atau "neutral" (opsional)
        days_back:        Cari dalam N hari terakhir (default 30, 0 = semua waktu)

    Requires: sentence-transformers + chromadb terinstall di venv
    """
    return _vec_search(
        query=query,
        n_results=n_results,
        group_filter=group_filter,
        sentiment_filter=sentiment_filter,
        days_back=days_back,
    )


@mcp.tool()
def telegram_vector_stats() -> dict:
    """Status vector store untuk semantic search — berapa vektor tersimpan, model yang dipakai.

    Gunakan ini untuk cek apakah semantic search sudah aktif dan siap dipakai.
    """
    return _vec_stats()


# ── IDX Fundamental Screener ───────────────────────────────────────────────────

@mcp.tool()
def idx_fundamental_screener(
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
    """Screen all ~860 IDX/BEI stocks by fundamental criteria using TradingView data.

    Returns market cap, P/E, P/B, P/S, ROE, dividend yield, debt/equity,
    revenue growth, EPS, gross/net margin, current ratio, sector, and industry
    for every IDX stock in a single call.

    Args:
        sort_by:            Column to sort by. Options:
                            market_cap, pe, pb, ps, roe, dividend_yield, de,
                            revenue_growth, eps, gross_margin, net_margin,
                            current_ratio, change, price, volume.
        ascending:          Sort direction. Default False (highest first).
        limit:              Max results. Default 50.
        sector:             Filter by sector (substring, case-insensitive).
                            Examples: "Finance", "Technology", "Consumer",
                            "Energy", "Healthcare", "Utilities", "Transportation".
        min_market_cap:     Minimum market cap in IDR trillion (e.g. 10.0 = 10T IDR).
        max_pe:             Maximum P/E ratio (TTM). Excludes negative P/E.
        min_roe:            Minimum Return on Equity % (e.g. 15 = 15%).
        min_dividend_yield: Minimum dividend yield % (e.g. 3 = 3%).
        max_de:             Maximum Debt/Equity ratio.
        min_revenue_growth: Minimum revenue growth % TTM.

    Examples:
        # Blue-chip value stocks
        idx_fundamental_screener(min_market_cap=50, max_pe=15, min_roe=15)

        # High-dividend income stocks
        idx_fundamental_screener(sort_by="dividend_yield", min_dividend_yield=5)

        # Best-quality banking sector
        idx_fundamental_screener(sector="Finance", sort_by="roe", min_roe=10)

        # Growth stocks with strong revenue
        idx_fundamental_screener(sort_by="revenue_growth", min_revenue_growth=20)

        # Low-debt profitable small caps
        idx_fundamental_screener(max_pe=10, max_de=0.5, min_roe=15, limit=20)
    """
    return screen_idx_fundamental(
        sort_by=sort_by,
        ascending=ascending,
        limit=limit,
        sector=sector,
        min_market_cap=min_market_cap,
        max_pe=max_pe,
        min_roe=min_roe,
        min_dividend_yield=min_dividend_yield,
        max_de=max_de,
        min_revenue_growth=min_revenue_growth,
    )


@mcp.tool()
def get_fibonacci_levels(
    ticker: str,
    lookback: str = "52W",
    timeframe: str = "1D",
) -> dict:
    """
    Fibonacci retracement & extension analysis untuk saham IDX.

    Menghitung 7 level retracement (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%)
    dan 3 level extension (127.2%, 161.8%, 261.8%) berdasarkan swing high/low.

    Sumber swing high/low (otomatis, priority order):
      1. TV Screener: 52W high/low, 6M, 3M, 1M (paling akurat)
      2. Pivot R3/S3 dari tradingview_ta (fallback)
      3. yfinance historical OHLCV (fallback terakhir)

    Output:
      - retracement_levels : 7 level dengan harga IDR
      - extension_levels   : 3 level proyeksi
      - key_levels         : jarak % ke tiap level dari harga saat ini
      - price_position     : zona saat ini, support/resistance Fib terdekat
      - golden pocket      : zona 61.8% (entry/reversal kunci)
      - context            : RSI, EMA50, EMA200, ATR%, volume ratio

    Lookback options: "1M", "3M", "6M", "52W" (default), "ALL"

    Contoh:
        get_fibonacci_levels("BBCA")
        get_fibonacci_levels("TLKM", lookback="3M")
        get_fibonacci_levels("ZATA", lookback="52W", timeframe="1W")
    """
    return analyze_idx_fibonacci(ticker=ticker, lookback=lookback, timeframe=timeframe)


@mcp.tool()
def get_stock_decision(
    ticker: str,
    timeframe: str = "1D",
) -> dict:
    """
    Keputusan investasi komprehensif untuk saham IDX (Bursa Efek Indonesia).

    Menggabungkan 3-layer technical scoring (100 poin) dengan Bandarmology Signal
    (OBV, CMF, MFI, VWAP, divergence detection) untuk output BUY / HOLD / SELL / AVOID.

    Layer A — Trend & Momentum (50 poin): EMA structure, RSI, MACD, relative performance
    Layer B — Konfirmasi (20 poin): volume ratio, ADX trend strength
    Layer C — Risk-Adjusted (15 poin): volatility control (ATR%), drawdown stability
    Layer D — Fundamental Overlay (15 poin): TV recommendation, MA+oscillator agreement
    Layer E — Bandarmology (±25 poin): OBV/CMF/MFI/VWAP money flow + divergence detection

    Liquidity: threshold berbasis IDR (traded value harian, volume lembar)
    Grade: Elite (85+) / Strong (70+) / Watchlist (55+) / Avoid (<55)
    Decision: BUY / HOLD / AVOID + confidence HIGH/MODERATE/LOW

    Contoh penggunaan:
        get_stock_decision("BBCA")
        get_stock_decision("TLKM", timeframe="1W")
        get_stock_decision("ZATA")
    """
    return get_idx_stock_decision(ticker=ticker, timeframe=timeframe)


@mcp.tool()
def get_advanced_indicators(ticker: str, timeframe: str = "1D") -> dict:
    """
    Indikator teknikal lanjutan: ADX/DMI, CCI, Williams %R, StochRSI,
    Stochastic Slow (10,5,5), Ichimoku Cloud, Volume Profile (POC/VAH/VAL).

    Lebih lengkap dari get_stock_decision — khusus untuk analisis mendalam.
    Ticker: kode saham IDX (BBCA, TLKM, dll). Timeframe: 1D (default), 1W, 4H.

    Sumber data:
      - tradingview_ta : ADX/DMI, CCI, Williams %R, StochRSI
      - yfinance + pandas_ta : Stochastic Slow (10,5,5), Ichimoku Cloud, Volume Profile

    Output:
      - adx_dmi       : ADX, +DI, -DI, signal (BULL/BEAR/NEUTRAL), strength (STRONG/MODERATE/WEAK)
      - cci           : CCI20 value + signal (OVERBOUGHT/OVERSOLD/NEUTRAL)
      - williams_r    : W%R value + signal (range -100 to 0)
      - stoch_rsi     : StochRSI K + signal
      - stoch_slow    : Stochastic Slow K/D (10,5,5) + signal (includes BULLISH_CROSS)
      - ichimoku      : Tenkan, Kijun, Span A/B, price_vs_cloud, signal
      - volume_profile: POC, VAH, VAL (70% value area), price_vs_poc

    Contoh:
        get_advanced_indicators("BBCA")
        get_advanced_indicators("TLKM", timeframe="1W")
    """
    return _get_advanced_indicators(
        ticker=ticker.upper().strip(),
        timeframe=sanitize_timeframe(timeframe, "1D"),
    )


# ── Resource ───────────────────────────────────────────────────────────────────

@mcp.resource("exchanges://list")
def exchanges_list() -> str:
    """List available exchanges from the coinlist directory."""
    try:
        current_dir = os.path.dirname(__file__)
        coinlist_dir = os.path.join(current_dir, "coinlist")
        if os.path.exists(coinlist_dir):
            exchanges = [
                f[:-4].upper()
                for f in os.listdir(coinlist_dir)
                if f.endswith(".txt")
            ]
            if exchanges:
                return f"Available exchanges: {', '.join(sorted(exchanges))}"
    except Exception:
        pass
    return "Common exchanges: KUCOIN, BINANCE, BYBIT, MEXC, BITGET, OKX, COINBASE, GATEIO, HUOBI, BITFINEX, KRAKEN, BITSTAMP, BIST, EGX, NASDAQ, TWSE, TPEX"


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TradingView Screener MCP server")
    parser.add_argument(
        "transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        nargs="?",
        help="Transport (default stdio)",
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    if os.environ.get("DEBUG_MCP"):
        import sys
        print(f"[DEBUG_MCP] pkg cwd={os.getcwd()} argv={sys.argv} file={__file__}", file=sys.stderr, flush=True)

    if args.transport == "stdio":
        mcp.run()
    else:
        try:
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        except Exception:
            pass
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
