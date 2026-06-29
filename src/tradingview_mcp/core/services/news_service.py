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

# ─── IDX Ticker → Company Name Aliases ───────────────────────────────────────
# Maps ticker code to list of name variants used in Indonesian news articles.
# News sites use company names, not ticker codes.
IDX_TICKER_ALIASES: dict[str, list[str]] = {
    "BBCA": ["BCA", "Bank BCA", "Bank Central Asia"],
    "BBRI": ["BRI", "Bank BRI", "Bank Rakyat Indonesia"],
    "BMRI": ["Bank Mandiri", "Mandiri"],
    "BBNI": ["BNI", "Bank BNI", "Bank Negara Indonesia"],
    "TLKM": ["Telkom", "Telekomunikasi Indonesia"],
    "ASII": ["Astra", "Astra International"],
    "UNVR": ["Unilever", "Unilever Indonesia"],
    "HMSP": ["HM Sampoerna", "Sampoerna"],
    "ICBP": ["Indofood CBP", "ICBP"],
    "INDF": ["Indofood", "Indofood Sukses Makmur"],
    "KLBF": ["Kalbe", "Kalbe Farma"],
    "UNTR": ["United Tractors"],
    "PGAS": ["PGN", "Perusahaan Gas Negara"],
    "PTBA": ["Bukit Asam", "PTBA"],
    "ADRO": ["Adaro", "Adaro Energy"],
    "ITMG": ["Indo Tambangraya", "ITMG"],
    "INCO": ["Vale Indonesia", "INCO"],
    "ANTM": ["Antam", "Aneka Tambang"],
    "MDKA": ["Merdeka Copper Gold", "MDKA"],
    "MBMA": ["Merdeka Battery", "MBMA"],
    "INKP": ["Indah Kiat", "Indah Kiat Pulp"],
    "TKIM": ["Pindo Deli", "Tjiwi Kimia"],
    "CTRA": ["Ciputra", "Ciputra Development"],
    "BSDE": ["BSD", "Bumi Serpong Damai"],
    "PWON": ["Pakuwon", "Pakuwon Jati"],
    "SMGR": ["Semen Indonesia", "Semen Gresik"],
    "INTP": ["Indocement", "Indo Cement"],
    "JSMR": ["Jasa Marga"],
    "WSKT": ["Waskita", "Waskita Karya"],
    "WIKA": ["Wijaya Karya", "WIKA"],
    "PTPP": ["PP Persero", "Pembangunan Perumahan"],
    "AKRA": ["AKR Corporindo", "AKR"],
    "EXCL": ["XL Axiata", "XL"],
    "ISAT": ["Indosat", "Indosat Ooredoo"],
    "TOWR": ["Sarana Menara", "Towel", "TOWR"],
    "MTEL": ["Mitratel", "MTEL"],
    "GOTO": ["GoTo", "Gojek", "Tokopedia"],
    "BUKA": ["Bukalapak"],
    "EMTK": ["Elang Mahkota", "EMTK"],
    "SCMA": ["Surya Citra", "SCTV"],
    "MNCN": ["Media Nusantara", "MNC"],
    "FILM": ["MD Pictures", "FILM"],
    "PANS": ["Panin Sekuritas", "PANS"],
    "SMRA": ["Summarecon", "Summarecon Agung"],
    "LPKR": ["Lippo Karawaci", "Lippo"],
    "MAPI": ["Mitra Adiperkasa", "MAP"],
    "ACES": ["Ace Hardware", "ACE"],
    "LPPF": ["Matahari Department", "Matahari"],
    "ERAA": ["Erajaya", "Erafone"],
    "SIDO": ["Sido Muncul"],
    "GGRM": ["Gudang Garam"],
    "BSSR": ["Baramulti", "BSSR"],
    "HRUM": ["Harum Energy", "HRUM"],
    "TPIA": ["Chandra Asri", "TPIA"],
    "BRPT": ["Barito Pacific", "Barito"],
    "MDIY": ["Mitra10", "MDIY"],
    # Telco & digital
    "WIFI": ["Solusi Sinergi Digital", "Solusinews", "WIFI"],
    "FREN": ["Smartfren", "Smart Telecom"],
    "HALO": ["Telkomsel", "HALO"],
    # Bank & finance
    "BRIS": ["Bank Syariah Indonesia", "BSI", "BRI Syariah"],
    "MEGA": ["Bank Mega"],
    "BNLI": ["Bank Permata", "Permata"],
    "BNGA": ["CIMB Niaga", "CIMB"],
    "NISP": ["Bank OCBC", "OCBC NISP"],
    "BDMN": ["Bank Danamon", "Danamon"],
    "BJBR": ["Bank BJB", "BJB"],
    "BJTM": ["Bank Jatim"],
    "AGRO": ["Bank Agro", "BRI Agro"],
    "PNBN": ["Bank Panin", "Panin"],
    # Consumer & retail
    "MYOR": ["Mayora", "Mayora Indah"],
    "ULTJ": ["Ultra Jaya", "UHT"],
    "ICBP": ["Indofood CBP"],
    "ROTI": ["Nippon Indosari", "Sari Roti"],
    "CLEO": ["Sariguna", "Cleo"],
    "CAMP": ["Campina"],
    "GOOD": ["Garudafood"],
    # Property
    "DMAS": ["Puradelta Lestari", "Deltamas"],
    "APLN": ["Agung Podomoro", "Podomoro"],
    "ASRI": ["Alam Sutera", "Alam Sutera Realty"],
    "KIJA": ["Kawasan Industri Jababeka", "Jababeka"],
    # Energy & mining
    "MEDC": ["Medco", "Medco Energi"],
    "ENRG": ["Energi Mega Persada"],
    "ELSA": ["Elnusa"],
    "RUIS": ["Radiant Utama"],
    "ESSA": ["ESSA Industries"],
    "HRUM": ["Harum Energy"],
    "INDY": ["Indika Energy", "Indika"],
    "BUMI": ["Bumi Resources"],
    "KKGI": ["Resource Alam Indonesia"],
    # Infrastructure & construction
    "TOLL": ["Margautama Nusantara"],
    "WTON": ["Wijaya Karya Beton", "WIKA Beton"],
    "ACST": ["Acset Indonusa"],
    # Healthcare & pharma
    "KAEF": ["Kimia Farma"],
    "KLBF": ["Kalbe", "Kalbe Farma"],
    "MIKA": ["Mitra Keluarga"],
    "SILO": ["Siloam Hospital", "Siloam"],
    "TSPC": ["Tempo Scan", "Tempo Scan Pacific"],
    "PYFA": ["Pyridam Farma"],
    # Auto & heavy equipment
    "ASSA": ["Adi Sarana Armada"],
    "HEXA": ["Hexindo Adiperkasa", "Hexindo"],
    "TURI": ["Tunas Ridean", "Tunas Toyota"],
    # Tech & startup
    "DMMX": ["Digital Mediatama", "DMMX"],
    "INET": ["Indointernet", "INET"],
    "MTDL": ["Metrodata Electronics", "Metrodata"],
    # Agribusiness
    "AALI": ["Astra Agro Lestari", "Astra Agro"],
    "LSIP": ["PP London Sumatra", "Lonsum"],
    "SSMS": ["Sawit Sumbermas", "SSMS"],
    "TAPG": ["Tunas Baru Lampung"],
    # Others mentioned in CIA groups
    "GOTO": ["GoTo", "Gojek", "Tokopedia", "Gotogroup"],
    "MAPA": ["Mitra Adiperkasa", "MAP", "Sports Station"],
    "RBMS": ["Ristia Bintang Mahkotasejati", "RBMS"],
    "MKAP": ["Cahayasakti Investindo", "MKAP"],
    "RGAS": ["Royalindo Investa Wijaya", "RGAS"],
    "KOCI": ["Koperasi Simpan Pinjam", "KOCI"],
    "VALM": ["Valentindo Surya", "VALM"],
    "VNOW": ["Venteny", "VNOW"],
    "TIRA": ["Tira Austenite", "TIRA"],
    "SCMA": ["Surya Citra", "SCTV", "Indosiar"],
    "EMTK": ["Elang Mahkota", "Emtek"],
    "MGNA": ["Magna Finance", "MGNA"],
}

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
    # Verified working (2026-06-29, text/xml confirmed):
    #   kontan ✓, cnbcindonesia ✓, idxchannel ✓, katadata ✓, detikfinance ✓
    # bisnis.com: no RSS, scraped from market.bisnis.com
    # Removed/not available:
    #   emitennews.com  → returns HTML bukan RSS (broken)
    #   pasarmodal.inilah.com → timeout
    #   idx.co.id → Cloudflare 403
    #   stockbit.com → Next.js SPA, tidak bisa di-scrape tanpa headless browser
    "indonesia": [
        {"url": "https://investasi.kontan.co.id/rss", "name": "Kontan Investasi"},
        {"url": "https://www.cnbcindonesia.com/market/rss", "name": "CNBC Indonesia Market"},
        {"url": "https://www.idxchannel.com/rss", "name": "IDX Channel"},
        {"url": "https://katadata.co.id/rss", "name": "Katadata"},
        {"url": "https://finance.detik.com/rss", "name": "Detik Finance"},
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

                # Symbol filter — match ticker OR any known company name alias
                if symbol:
                    combined = f"{title} {summary}".upper()
                    search_terms = [symbol.upper()]
                    search_terms += [alias.upper() for alias in IDX_TICKER_ALIASES.get(symbol.upper(), [])]
                    if not any(term in combined for term in search_terms):
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
            sym_terms = [symbol.upper()] + [a.upper() for a in IDX_TICKER_ALIASES.get(symbol.upper(), [])]
            scraped = [
                a for a in scraped
                if any(term in a["title"].upper() for term in sym_terms)
            ]
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
