"""
Financial News Service via RSS feeds + HTML scraping fallback.

Uses feedparser (already installed as part of agent-reach dependencies).
No API keys required. Pulls from free, public RSS feeds.

Sources:
  crypto:    CoinDesk, Cointelegraph
  stocks:    Yahoo Finance, MarketWatch (Top + Real-Time), CNBC
  indonesia: Kontan, CNBC Indonesia, IDX Channel, Katadata, Emiten News,
             Bisnis.com Market (scraped — no RSS available)
  all:       Combined

Note (2026-05-14): Original Reuters feeds (feeds.reuters.com) are deprecated
since ~2020 — they return zero entries. Replaced with Yahoo Finance,
MarketWatch, and CNBC which return live data. A `User-Agent` header is
required for some publishers (Yahoo, CNBC) to serve the feed correctly.
"""
from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timezone
from typing import Optional

# feedparser is bundled with agent-reach (installed globally)
try:
    import feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _FEEDPARSER_AVAILABLE = False

# ─── Feed Catalog ─────────────────────────────────────────────────────────────

RSS_FEEDS: dict[str, list[dict]] = {
    "crypto": [
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "name": "CoinDesk"},
        {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph"},
    ],
    "stocks": [
        {"url": "https://finance.yahoo.com/news/rssindex", "name": "Yahoo Finance"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "name": "MarketWatch Top Stories"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", "name": "MarketWatch Real-Time"},
        {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "name": "CNBC Top News"},
    ],
    # Indonesian stock market news — IDX/BEI focused
    # Verified working (2026-06): kontan ✓, cnbcindonesia ✓, idxchannel ✓, katadata ✓, emitennews ✓
    # bisnis.com: no RSS, scraped from market.bisnis.com
    # Removed: pasarmodal.inilah.com (timeout), idx.co.id (Cloudflare 403)
    "indonesia": [
        {"url": "https://investasi.kontan.co.id/rss", "name": "Kontan Investasi"},
        {"url": "https://www.cnbcindonesia.com/market/rss", "name": "CNBC Indonesia Market"},
        {"url": "https://www.idxchannel.com/rss", "name": "IDX Channel"},
        {"url": "https://katadata.co.id/rss", "name": "Katadata"},
        {"url": "https://emitennews.com/?feed=rss2", "name": "Emiten News"},
    ],
    "all": [
        {"url": "https://finance.yahoo.com/news/rssindex", "name": "Yahoo Finance"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "name": "MarketWatch Top Stories"},
        {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "name": "CNBC Top News"},
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "name": "CoinDesk"},
        {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph"},
    ],
}

# Some publishers (Yahoo, CNBC) return empty feeds to the default urllib UA.
# Setting a browser-like UA produces live data.
_FEED_USER_AGENT = "Mozilla/5.0 (compatible; tradingview-mcp/0.7.1; +https://github.com/atilaahmettaner/tradingview-mcp)"
_TIMEOUT = 8


# ─── Bisnis.com scraper (no RSS available) ────────────────────────────────────

def _scrape_bisnis_market(limit: int = 10) -> list[dict]:
    """
    Scrape article headlines from market.bisnis.com.
    URL pattern: /read/YYYYMMDD/<section_id>/<article_id>/<slug>
    Falls back silently to empty list on any error.
    """
    try:
        req = urllib.request.Request(
            "https://market.bisnis.com",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    # Extract article URLs and deduplicate
    urls = list(dict.fromkeys(
        re.findall(r'https://market\.bisnis\.com/read/\d{8}/\d+/\d+/[^"\'<>\s]+', html)
    ))

    results: list[dict] = []
    for url in urls[:limit]:
        # Derive title from slug: last path segment, replace hyphens
        slug = url.rstrip("/").split("/")[-1]
        title = slug.replace("-", " ").title()
        # Extract date from URL: /read/YYYYMMDD/
        date_match = re.search(r'/read/(\d{4})(\d{2})(\d{2})/', url)
        published = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else ""
        results.append({
            "title": title,
            "url": url,
            "published": published,
            "summary": "",
            "source": "Bisnis.com Market",
        })

    return results[:limit]


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_news(
    symbol: Optional[str] = None,
    category: str = "stocks",
    limit: int = 10,
) -> list[dict]:
    """
    Fetch financial news from RSS feeds (+ HTML scraping for bisnis.com).

    Args:
        symbol:   Optional ticker filter. If provided, only returns headlines
                  that mention the symbol (case-insensitive). e.g. "AAPL", "BTC"
        category: Feed group — "crypto" | "stocks" | "indonesia" | "all"
        limit:    Maximum number of items to return

    Returns:
        List of news items with title, url, published, summary, source.
    """
    if not _FEEDPARSER_AVAILABLE:
        return [{
            "error": "feedparser not installed. Run: pip install feedparser",
            "install": "pip install feedparser"
        }]

    feeds = RSS_FEEDS.get(category, RSS_FEEDS["stocks"])
    results: list[dict] = []

    for feed_info in feeds:
        if len(results) >= limit:
            break
        try:
            feed = feedparser.parse(feed_info["url"], agent=_FEED_USER_AGENT)
            source_name = feed.feed.get("title", feed_info["name"])

            for entry in feed.entries:
                if len(results) >= limit:
                    break

                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")

                # Symbol filter
                if symbol:
                    combined = f"{title} {summary}".upper()
                    if symbol.upper() not in combined:
                        continue

                results.append({
                    "title": title,
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": _clean_html(summary)[:300],
                    "source": source_name,
                })

        except Exception:
            continue

    # Append bisnis.com scraped articles for indonesia category
    if category == "indonesia" and len(results) < limit:
        remaining = limit - len(results)
        scraped = _scrape_bisnis_market(limit=remaining)
        if symbol:
            scraped = [a for a in scraped if symbol.upper() in a["title"].upper()]
        results.extend(scraped)

    return results[:limit]


def fetch_news_summary(
    symbol: Optional[str] = None,
    category: str = "stocks",
    limit: int = 10,
) -> dict:
    """
    Fetch news and return structured dict for MCP tool output.
    """
    items = fetch_news(symbol, category, limit)
    return {
        "symbol": symbol,
        "category": category,
        "count": len(items),
        "feedparser_available": _FEEDPARSER_AVAILABLE,
        "items": items,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Utils ────────────────────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """Strip basic HTML tags from text."""
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return text.strip()
