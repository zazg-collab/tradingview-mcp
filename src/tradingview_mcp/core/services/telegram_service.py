"""
Telegram Reader Service — via Telethon (MTProto User API).

Membaca pesan dari grup/channel Telegram menggunakan akun user biasa
(bukan bot), sehingga bisa akses grup private sekalipun.

Setup (SATU KALI dari Mac terminal):
    cd ~/mcp-atila
    venv/bin/pip install telethon
    python scripts/telegram_auth.py
    # Masukkan nomor HP, kode OTP, dan 2FA password jika ada
    # Session tersimpan di ~/.mcp_atila_telegram.session

Setelah itu semua tools di sini langsung bisa dipakai tanpa auth ulang.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

SESSION_FILE = os.path.expanduser("~/.mcp_atila_telegram.session")
_DB_PATH     = os.path.expanduser("~/.mcp_atila_knowledge.db")
_MEDIA_DIR   = os.path.expanduser("~/.mcp_atila_media")

try:
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    from telethon.tl.types import (
        Message, Channel, Chat, User,
        MessageMediaDocument, MessageMediaPhoto,
        DocumentAttributeFilename,
        DialogFilter, DialogFilterDefault,
    )
    from telethon.errors import SessionPasswordNeededError, FloodWaitError
    _TELETHON_OK = True
except ImportError:
    _TELETHON_OK = False

try:
    import pdfplumber
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

# Semantic vector search (lazy import — tidak wajib)
try:
    from tradingview_mcp.core.services.vector_service import index_message as _vec_index
    _VECTOR_OK = True
except ImportError:
    _VECTOR_OK = False
    def _vec_index(*args, **kwargs): return False  # noqa: E731

# ── IDX Ticker Recognition ─────────────────────────────────────────────────────
#
# STRATEGI 3-LAYER (lebih akurat dari blacklist/skip-words):
#
#   Layer 1 — Case-sensitive: hanya match kata yang SUDAH ALL-CAPS di teks asli.
#              "nonton film" → tidak match. "FILM breakout" → match.
#
#   Layer 2 — Whitelist: hanya terima kata yang ada di daftar ticker IDX resmi.
#              Mencegah false positive dari kata umum yang tidak ada di IDX.
#
#   Layer 3 — Context (untuk ticker ambigu): ticker yang juga kata sehari-hari
#              (FILM, ROTI, HALO, dll) wajib ada kata konteks saham di sekitarnya,
#              atau angka harga, atau bersamaan dengan ticker lain yang jelas.
#
# Kenapa whitelist lebih baik dari blacklist?
# IDX punya ~900 ticker. Blacklist kata-kata umum selalu incomplete dan rawan
# salah (sempat BUKA, MEJA, STAR, dll masuk blacklist padahal ticker IDX beneran).
# Whitelist membalik logika: hanya terima yang KITA KENAL sebagai ticker.

_TICKER_RE = re.compile(r'\b([A-Z]{4})\b')

# ── Whitelist: ticker IDX yang diketahui ──────────────────────────────────────
# Mencakup LQ45, IDX80, mid-cap populer, dan saham yang sering dibahas di CIA.
# Update berkala jika ada emiten baru masuk watchlist.
_IDX_TICKERS: frozenset = frozenset({
    # Blue chips / LQ45 / IDX30
    "BBCA","BBRI","BMRI","BBNI","TLKM","ASII","BREN","TPIA","BRPT","UNVR",
    "INDF","ICBP","HMSP","GGRM","KLBF","SIDO","MIKA","HEAL","UNTR","PGAS",
    "PTBA","ADRO","INCO","ANTM","MDKA","MBMA","INKP","TKIM","AKRA","JSMR",
    "SMGR","INTP","EXCL","ISAT","TOWR","MTEL","CTRA","BSDE","PWON","SMRA",
    # Banking & finance
    "BRIS","MEGA","NISP","BDMN","BJBR","BJTM","PNBN","BNLI","BNGA","AGRO",
    "PANS","ARTO","BMAS","BACA","DNAR","LPBN","BGTG","MCOR","BBYB","NOBU",
    # Tech & digital media
    "GOTO","BUKA","EMTK","WIFI","INET","MTDL","DMMX","MNCN","SCMA","FILM",
    "FREN","HALO","VNOW","DCII","DIGI","LIVE",
    # Mining & energy
    "BSSR","HRUM","ITMG","INDY","BUMI","MEDC","ENRG","ELSA","ESSA","KKGI",
    "PGEO","RGAS","OILS","DSSA","AADI","ARII","CGAS","MBSS","TOBA","SMMT",
    "FIRE","ZINC","CNKO","PKPK","GTBO","MYOH","DEWA","SGER","DOID","MBAP",
    "ITMG","PTRO","HPAI","ATPK","BRMS","BYAN","COAL","GEMS",
    # Consumer goods
    "MYOR","ROTI","CLEO","GOOD","ULTJ","CAMP","TSPC","KAEF","PYFA",
    "DLTA","MLBI","ADES","PSDN","AISA","LMSH","CEKA","TBLA","KINO","PRTA",
    # Property & construction
    "LPKR","DMAS","APLN","ASRI","KIJA","WSKT","WIKA","PTPP","WTON","ACST",
    "TOLL","BCIP","EMDE","NIRO","MDLN","BKSL","PPRO","RODA","GWSA","CITY",
    "MEJA","PLIN","MKPI","GPRA","SMDM","DUTI",
    # Retail & lifestyle
    "ACES","LPPF","ERAA","ASSA","MAPA","MPPA","LILA","CSAP","HERO","MAPI",
    # Healthcare
    "SILO","HEAL","PRDA","IRRA","BMHS","RSGK","KPIG",
    # Infrastructure & transport
    "BIRD","GIAA","CMPP","PORT","SAFE","HITS","NELY","TPMA","BULL","BPTR",
    # Agribusiness
    "AALI","LSIP","SSMS","TAPG","BWPT","SGRO","PALM","SIMP","GZCO",
    # Telco & tower
    "CENT","TBIG","SUPR","GOLD",
    # Others frequently discussed in CIA groups
    "KOCI","EPAC","ESIP","MMIX","STAR","ICON","RBMS","MKAP","VALM","TIRA",
    "MGNA","MDIY","KBAG","CUAN","NICL","NCKL","CBPE","ISSP","KOKA","KMDS",
    "ESTI","LPCK","LPKR","SRTG","WIFI","RGAS","PSAT","AXIO","BOAT",
})

# ── Ambiguous: ticker IDX yang juga kata sehari-hari ─────────────────────────
# Untuk ticker ini, wajib ada konteks saham di dekatnya sebelum dianggap ticker.
#
# Contoh false positive yang bisa terjadi:
#   FILM  → "nonton FILM tadi" (film = movie)
#   ROTI  → "makan ROTI bakar" (roti = bread)
#   HALO  → "HALO guys selamat pagi" (halo = greeting)
#   GOOD  → "hasil GOOD banget hari ini" (good = quality adjective)
#   BUKA  → "BUKA puasa jam 6" (buka = open, Ramadan context)
#   WIFI  → "connect ke WIFI dulu" (wifi = internet tech)
#   BULL  → "sentimen BULL sedang kuat" (bull = market term, bukan ticker)
#   FIRE  → "FIRE exit ada di sini" (fire = kebakaran)
#   OILS  → "OILS and gas sector" (oils = plural noun)
#   STAR  → "bintang / STAR Wars" (star = bintang)
_AMBIGUOUS_TICKERS: frozenset = frozenset({
    "FILM","ROTI","HALO","GOOD","BUKA","WIFI","BULL","FIRE","OILS","STAR",
    "TOLL","HEAL","CAMP","HERO","SAFE","PORT","CITY","SILO","ICON","BIRD",
    "CLEO","MEGA","AGRO","ACES","ZINC","BREN","ELSA","LIVE","DIGI","GOLD",
})

# ── Kata konteks saham ────────────────────────────────────────────────────────
# Kemunculan salah satu kata ini di dekat ticker ambigu → dianggap konteks saham.
_STOCK_CTX: frozenset = frozenset({
    # Istilah saham Indonesia
    "SAHAM","EMITEN","ANALISA","TEKNIKAL","FUNDAMENTAL","AKUMULASI",
    "DISTRIBUSI","BREAKOUT","BREAKDOWN","REVERSAL","KOLEKSI","REKOMEN",
    "REKOMENDASI","PORTOFOLIO","DIVIDEN","BANDAR","BANDARMOLOGY","AVERAGING",
    "CUTLOSS","SINYAL","ALERT","UPTREND","DOWNTREND",
    # Pasar / exchange
    "IHSG","IDX","BEI","BURSA","LQ45",
    # Indikator teknikal (dalam konteks analisa)
    "RESISTANCE","SUPPORT","FIBONACCI","PIVOT","OVERBOUGHT","OVERSOLD",
    "BOLLINGER","STOCHASTIC","VOLUME","MACD","EMA","SMA","RSI",
    # Terminologi posisi
    "BULLISH","BEARISH","LONGTERM","SWING","SCALP","INTRADAY",
    # CIA group-specific signals
    "INSIDER","ACCUMULATION","ACCUMULATE","DISTRIBUTION",
    "TP1","TP2","TP3","SL1","SL2","CL1",
})


_CREDS_FILE = os.path.expanduser("~/.mcp_atila_credentials.json")

def _get_credentials() -> tuple[int, str]:
    """Load api_id and api_hash — dari env vars atau ~/.mcp_atila_credentials.json."""
    import json as _json

    api_id   = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")

    # Fallback: baca dari file credentials lokal
    if (not api_id or not api_hash) and os.path.exists(_CREDS_FILE):
        try:
            creds  = _json.loads(open(_CREDS_FILE).read())
            api_id   = api_id   or str(creds.get("TELEGRAM_API_ID", ""))
            api_hash = api_hash or str(creds.get("TELEGRAM_API_HASH", ""))
        except Exception:
            pass

    if not api_id or not api_hash:
        raise EnvironmentError(
            "Credentials belum di-set. Buat file ~/.mcp_atila_credentials.json:\n"
            '{"TELEGRAM_API_ID": 12345, "TELEGRAM_API_HASH": "abcdef..."}\n'
            "Atau set env: TELEGRAM_API_ID dan TELEGRAM_API_HASH"
        )
    return int(api_id), api_hash


def _run(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _not_available(feature: str) -> dict:
    return {
        "success": False,
        "error": "telethon tidak terinstall",
        "fix": "cd ~/mcp-atila && venv/bin/pip install telethon",
        "feature": feature,
    }


def _no_session() -> dict:
    return {
        "success": False,
        "error": "Belum login Telegram. Jalankan setup auth dulu.",
        "fix": "cd ~/mcp-atila && python scripts/telegram_auth.py",
        "session_path": SESSION_FILE,
    }


# ── Sentiment Analysis Helper ─────────────────────────────────────────────────

_BULLISH_WORDS = [
    "beli", "buy", "naik", "up", "bullish", "breakout", "kuat", "mantap",
    "bagus", "rebound", "accumulate", "akumulasi", "hold", "target", "murah",
    "undervalue", "potensi", "rekomendasi", "recom", "masuk", "entry",
    "golden cross", "support", "mantul", "bounce", "oke", "oke banget",
    "all time high", "ath", "auto", "cuan", "profit", "untung",
]

_BEARISH_WORDS = [
    "jual", "sell", "turun", "down", "bearish", "breakdown", "lemah", "jelek",
    "rugi", "loss", "cut loss", "cutloss", "stop loss", "sl", "hindari",
    "avoid", "waspada", "hati-hati", "distribusi", "distribution", "keluar",
    "exit", "death cross", "resistance", "mahal", "overvalue", "nyangkut",
    "boncos", "merah",
]

def _analyze_sentiment(texts: list[str]) -> dict:
    """Simple keyword-based sentiment dari list teks pesan."""
    bull = 0
    bear = 0
    neutral = 0

    for text in texts:
        t = text.lower()
        b_score = sum(1 for w in _BULLISH_WORDS if w in t)
        s_score = sum(1 for w in _BEARISH_WORDS if w in t)
        if b_score > s_score:
            bull += 1
        elif s_score > b_score:
            bear += 1
        else:
            neutral += 1

    total = bull + bear + neutral
    if total == 0:
        return {"label": "No Data", "score": 0, "bullish": 0, "bearish": 0, "neutral": 0}

    net = (bull - bear) / total
    if net > 0.3:    label = "Bullish"
    elif net > 0.1:  label = "Mildly Bullish"
    elif net < -0.3: label = "Bearish"
    elif net < -0.1: label = "Mildly Bearish"
    else:            label = "Neutral"

    return {
        "label":   label,
        "score":   round(net, 3),
        "bullish": bull,
        "bearish": bear,
        "neutral": neutral,
        "total":   total,
    }


# ── Knowledge Base (SQLite) ───────────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    os.makedirs(_MEDIA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id      INTEGER,
            group_name  TEXT,
            group_id    TEXT,
            sender      TEXT,
            date        TEXT,
            text        TEXT,
            media_type  TEXT,
            media_text  TEXT,
            tickers     TEXT,
            sentiment   TEXT,
            indexed_at  TEXT,
            UNIQUE(msg_id, group_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ticker ON messages(tickers);
        CREATE INDEX IF NOT EXISTS idx_date   ON messages(date);
        CREATE INDEX IF NOT EXISTS idx_group  ON messages(group_name);
    """)
    conn.commit()
    return conn


def _has_stock_context(text: str, ticker: str) -> bool:
    """Return True jika ticker ambigu muncul dalam konteks diskusi saham.

    Cara kerja:
    1. Buat window 150 karakter di sekitar posisi ticker dalam teks
    2. Cek apakah ada kata konteks saham (_STOCK_CTX) dalam window
    3. Cek apakah ada angka harga (3-6 digit) atau simbol % di sekitarnya
    4. Cek apakah ada ticker IDX lain (non-ambigu) dalam pesan yang sama →
       bila ya, kemungkinan besar ini diskusi saham
    """
    text_up = text.upper()
    pos     = 0
    while True:
        idx = text_up.find(ticker, pos)
        if idx == -1:
            break
        window = text_up[max(0, idx - 150): idx + len(ticker) + 150]

        # Konteks kata saham
        if any(w in window for w in _STOCK_CTX):
            return True
        # Angka harga (mis. "FILM 1500", "ROTI 1.250")
        if re.search(r'\b\d{3,6}\b', window):
            return True
        # Persentase
        if "%" in window:
            return True
        # Satuan lot
        if re.search(r'\b\d+\s*LOT\b', window):
            return True

        pos = idx + 1

    # Jika ada ticker IDX lain (tidak ambigu) dalam pesan → kemungkinan list saham
    confirmed_others = [
        t for t in _TICKER_RE.findall(text)
        if t in _IDX_TICKERS and t != ticker and t not in _AMBIGUOUS_TICKERS
    ]
    return len(confirmed_others) >= 1


def _extract_tickers(text: str) -> list[str]:
    """Extract kode saham IDX dari teks pesan — 3-layer filter.

    Layer 1 — Case-sensitive:
        Hanya cocokkan kata yang sudah ALL-CAPS di teks asli.
        "nonton film tadi" → FILM tidak match (lowercase).
        "FILM breakout!" → FILM match.

    Layer 2 — Whitelist IDX:
        Hanya terima kata yang ada di _IDX_TICKERS (daftar emiten resmi IDX).
        Kata umum yang tidak terdaftar di IDX (UANG, DUIT, INFO, FAST, dll)
        otomatis gugur meski ditulis kapital.

    Layer 3 — Context check (ticker ambigu):
        Ticker yang juga kata sehari-hari (FILM=movie, ROTI=bread, HALO=hello,
        GOOD=bagus, BUKA=open, WIFI=internet, dll) wajib ditemani kata konteks
        saham, angka harga, atau ticker IDX lain dalam pesan yang sama.
        Tanpa konteks → dianggap kata biasa, bukan ticker.
    """
    if not text:
        return []

    # Layer 1: ALL-CAPS di teks asli (BUKAN text.upper())
    candidates = _TICKER_RE.findall(text)
    if not candidates:
        return []

    # Layer 2: whitelist IDX
    known = [t for t in candidates if t in _IDX_TICKERS]
    if not known:
        return []

    # Layer 3: context check untuk ticker ambigu
    result: list[str] = []
    for ticker in known:
        if ticker in _AMBIGUOUS_TICKERS:
            if _has_stock_context(text, ticker):
                result.append(ticker)
        else:
            result.append(ticker)

    return list(set(result))


def _save_message(msg_id: int, group_name: str, group_id: str, sender: str,
                  date: str, text: str, media_type: str, media_text: str,
                  sentiment: str) -> None:
    tickers = ",".join(_extract_tickers(f"{text} {media_text}"))
    conn = _init_db()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO messages
            (msg_id, group_name, group_id, sender, date, text, media_type,
             media_text, tickers, sentiment, indexed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (msg_id, group_name, group_id, sender, date,
              text[:800], media_type, media_text[:800],
              tickers, sentiment,
              datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()

    # Auto-index ke vector store (semantic search) — non-blocking, skip kalau belum install
    combined_text = f"{text} {media_text}".strip()
    if combined_text and len(combined_text) >= 10:
        doc_id = f"{group_id}_{msg_id}"
        _vec_index(
            msg_id   = doc_id,
            text     = combined_text[:800],
            group_name = group_name,
            sender   = sender or "",
            date     = date or "",
            tickers  = tickers,
            sentiment = sentiment,
        )


# ── PDF extraction ─────────────────────────────────────────────────────────────

async def _extract_pdf(client, msg) -> str:
    if not _PDF_OK:
        return "[PDF: install pdfplumber — pip install pdfplumber]"
    try:
        path = await client.download_media(msg, file=_MEDIA_DIR)
        if path and str(path).lower().endswith(".pdf"):
            with pdfplumber.open(path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages[:8]]
            return "\n".join(pages)[:4000]
        return f"[File: {path}]"
    except Exception as e:
        return f"[PDF error: {e}]"


# ── Core async functions ───────────────────────────────────────────────────────

async def _read_messages_async(
    chat_identifier: str,
    limit:       int = 50,
    keyword:     Optional[str] = None,
    hours_back:  int = 24,
    save_to_db:  bool = True,
    extract_pdf: bool = True,
) -> list[dict]:
    """Baca pesan dari chat/grup/channel — support text, PDF, photo."""
    api_id, api_hash = _get_credentials()

    async with TelegramClient(SESSION_FILE, api_id, api_hash) as client:
        entity     = await client.get_entity(chat_identifier)
        group_name = getattr(entity, "title", str(chat_identifier))
        group_id   = str(entity.id)
        cutoff     = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        messages = []
        async for msg in client.iter_messages(entity, limit=limit * 4):
            if not msg:
                continue

            msg_date = msg.date.replace(tzinfo=timezone.utc) if msg.date else None
            if msg_date and msg_date < cutoff:
                break

            text       = msg.text or ""
            media_type = ""
            media_text = ""

            # Handle media attachments
            if msg.media:
                if isinstance(msg.media, MessageMediaDocument):
                    attrs = getattr(msg.media.document, "attributes", [])
                    fname = next(
                        (a.file_name for a in attrs
                         if isinstance(a, DocumentAttributeFilename)), ""
                    )
                    if fname.lower().endswith(".pdf") and extract_pdf:
                        media_type = "pdf"
                        media_text = await _extract_pdf(client, msg)
                    else:
                        media_type = "document"
                        media_text = f"[{fname}]"
                elif isinstance(msg.media, MessageMediaPhoto):
                    media_type = "photo"
                    media_text = "[Foto]"

            combined = f"{text} {media_text}".strip()
            if not combined:
                continue

            # Keyword filter
            if keyword and keyword.lower() not in combined.lower():
                continue

            # Sender
            sender_name = "Unknown"
            try:
                if msg.sender:
                    s = msg.sender
                    if hasattr(s, "first_name"):
                        sender_name = ((s.first_name or "") + (" " + s.last_name if s.last_name else "")).strip()
                    elif hasattr(s, "title"):
                        sender_name = s.title
                    if not sender_name:
                        sender_name = getattr(s, "username", "unknown") or "unknown"
            except Exception:
                pass

            tickers   = _extract_tickers(combined)
            sent_dict = _analyze_sentiment([combined])
            sentiment = sent_dict.get("label", "Neutral").lower()
            date_str  = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""

            row = {
                "id":         msg.id,
                "date":       date_str,
                "sender":     sender_name,
                "text":       text[:500],
                "media_type": media_type,
                "media_text": media_text[:300] if media_text else "",
                "tickers":    tickers,
                "sentiment":  sentiment,
                "views":      getattr(msg, "views", None),
                "forwards":   getattr(msg, "forwards", None),
            }
            messages.append(row)

            # Auto-save to knowledge base
            if save_to_db:
                _save_message(
                    msg_id=msg.id, group_name=group_name, group_id=group_id,
                    sender=sender_name, date=date_str,
                    text=text, media_type=media_type, media_text=media_text,
                    sentiment=sentiment,
                )

            if len(messages) >= limit:
                break

        return messages


async def _list_folders_async() -> list[dict]:
    """List semua folder/filter Telegram yang dibuat user."""
    api_id, api_hash = _get_credentials()
    async with TelegramClient(SESSION_FILE, api_id, api_hash) as client:
        result = await client(GetDialogFiltersRequest())
        folders = []
        for f in result.filters:
            if isinstance(f, DialogFilterDefault):
                continue  # Skip "All Chats" default
            folders.append({
                "id":    f.id,
                "title": f.title.text if hasattr(f.title, "text") else str(f.title),
                "peer_count": len(getattr(f, "include_peers", [])),
            })
        return folders


async def _read_folder_async(
    folder_name:  str,
    limit_per_chat: int = 50,
    hours_back:   int = 24,
    ticker_filter: Optional[str] = None,
    save_to_db:   bool = True,
) -> dict:
    """Baca semua grup dalam satu folder Telegram sekaligus."""
    api_id, api_hash = _get_credentials()

    async with TelegramClient(SESSION_FILE, api_id, api_hash) as client:
        # Get folder list
        result   = await client(GetDialogFiltersRequest())
        target   = None
        for f in result.filters:
            if isinstance(f, DialogFilterDefault):
                continue
            title = f.title.text if hasattr(f.title, "text") else str(f.title)
            if folder_name.lower() in title.lower():
                target = f
                break

        if not target:
            return {
                "success": False,
                "error":   f"Folder '{folder_name}' tidak ditemukan",
                "available_folders": [
                    f.title.text if hasattr(f.title, "text") else str(f.title)
                    for f in result.filters
                    if not isinstance(f, DialogFilterDefault)
                ],
            }

        folder_title = target.title.text if hasattr(target.title, "text") else str(target.title)
        peers        = getattr(target, "include_peers", [])

        all_messages = []
        chat_summaries = []
        errors = []

        for peer in peers:
            try:
                entity     = await client.get_entity(peer)
                chat_name  = getattr(entity, "title", None) or getattr(entity, "first_name", str(peer))
                chat_id    = str(entity.id)
                cutoff     = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                chat_msgs  = []

                async for msg in client.iter_messages(entity, limit=limit_per_chat * 3):
                    if not msg:
                        continue
                    msg_date = msg.date.replace(tzinfo=timezone.utc) if msg.date else None
                    if msg_date and msg_date < cutoff:
                        break

                    text       = msg.text or ""
                    media_type = ""
                    media_text = ""

                    if msg.media:
                        if isinstance(msg.media, MessageMediaDocument):
                            attrs = getattr(msg.media.document, "attributes", [])
                            fname = next((a.file_name for a in attrs
                                          if isinstance(a, DocumentAttributeFilename)), "")
                            if fname.lower().endswith(".pdf"):
                                media_type = "pdf"
                                media_text = await _extract_pdf(client, msg)
                            else:
                                media_type = "document"
                                media_text = f"[{fname}]"
                        elif isinstance(msg.media, MessageMediaPhoto):
                            media_type = "photo"
                            media_text = "[Foto]"

                    combined = f"{text} {media_text}".strip()
                    if not combined:
                        continue
                    if ticker_filter and ticker_filter.upper() not in combined.upper():
                        tickers = _extract_tickers(combined)
                        if ticker_filter.upper() not in tickers:
                            continue

                    tickers   = _extract_tickers(combined)
                    sent_dict = _analyze_sentiment([combined])
                    sentiment = sent_dict.get("label", "Neutral").lower()
                    date_str  = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""

                    sender_name = "unknown"
                    try:
                        if msg.sender:
                            s = msg.sender
                            sender_name = ((getattr(s, "first_name", "") or "") +
                                           (" " + getattr(s, "last_name", "") if getattr(s, "last_name", "") else "")).strip()
                            if not sender_name:
                                sender_name = getattr(s, "title", "") or getattr(s, "username", "unknown") or "unknown"
                    except Exception:
                        pass

                    row = {
                        "chat":       chat_name,
                        "id":         msg.id,
                        "date":       date_str,
                        "sender":     sender_name,
                        "text":       text[:400],
                        "media_type": media_type,
                        "media_text": media_text[:200] if media_text else "",
                        "tickers":    tickers,
                        "sentiment":  sentiment,
                    }
                    chat_msgs.append(row)
                    all_messages.append(row)

                    if save_to_db:
                        _save_message(
                            msg_id=msg.id, group_name=chat_name, group_id=chat_id,
                            sender=sender_name, date=date_str,
                            text=text, media_type=media_type, media_text=media_text,
                            sentiment=sentiment,
                        )

                    if len(chat_msgs) >= limit_per_chat:
                        break

                # Per-chat sentiment
                chat_texts = [m["text"] for m in chat_msgs]
                chat_sent  = _analyze_sentiment(chat_texts)
                chat_summaries.append({
                    "chat":      chat_name,
                    "messages":  len(chat_msgs),
                    "sentiment": chat_sent.get("label", "Neutral"),
                })

            except Exception as e:
                errors.append({"chat": str(peer), "error": str(e)})
                continue

        # Aggregate tickers & sentiment
        ticker_count: dict[str, int] = {}
        for m in all_messages:
            for t in m.get("tickers", []):
                ticker_count[t] = ticker_count.get(t, 0) + 1

        top_tickers = sorted(ticker_count.items(), key=lambda x: x[1], reverse=True)[:15]
        combined_sent = _analyze_sentiment([m["text"] for m in all_messages])

        return {
            "success":        True,
            "folder":         folder_title,
            "chats_scanned":  len(chat_summaries),
            "total_messages": len(all_messages),
            "hours_back":     hours_back,
            "ticker_filter":  ticker_filter,
            "combined_sentiment": combined_sent,
            "top_tickers":    [{"ticker": t, "mentions": c} for t, c in top_tickers],
            "per_chat":       chat_summaries,
            "errors":         errors,
            "messages":       all_messages[:30],  # preview 30 pesan
        }


async def _list_chats_async(limit: int = 30) -> list[dict]:
    """List semua dialog (grup, channel, DM) yang aktif."""
    api_id, api_hash = _get_credentials()

    async with TelegramClient(SESSION_FILE, api_id, api_hash) as client:
        chats = []
        async for dialog in client.iter_dialogs(limit=limit):
            entity = dialog.entity
            chat_type = "unknown"
            if hasattr(entity, "megagroup") and entity.megagroup:
                chat_type = "supergroup"
            elif hasattr(entity, "broadcast") and entity.broadcast:
                chat_type = "channel"
            elif isinstance(entity, Chat):
                chat_type = "group"
            elif isinstance(entity, User):
                chat_type = "user"

            chats.append({
                "name":       dialog.name,
                "id":         dialog.id,
                "type":       chat_type,
                "unread":     dialog.unread_count,
                "username":   getattr(entity, "username", None),
                "identifier": f"@{entity.username}" if getattr(entity, "username", None) else str(dialog.id),
            })
        return chats


# ── Public API ────────────────────────────────────────────────────────────────

def telegram_read_messages(
    chat: str,
    limit: int = 50,
    keyword: Optional[str] = None,
    hours_back: int = 24,
) -> dict:
    """
    Baca pesan terbaru dari grup/channel Telegram.

    Args:
        chat:       Username (@sahamindo) atau ID numerik grup/channel
        limit:      Jumlah pesan max (default 50)
        keyword:    Filter pesan yang mengandung kata ini (optional)
        hours_back: Baca pesan N jam terakhir (default 24)
    """
    if not _TELETHON_OK:
        return _not_available("telegram_read_messages")
    if not os.path.exists(SESSION_FILE):
        return _no_session()

    try:
        messages = _run(_read_messages_async(chat, limit, keyword, hours_back))
        sentiment = _analyze_sentiment([m["text"] for m in messages])
        return {
            "success":   True,
            "chat":      chat,
            "keyword":   keyword,
            "hours_back": hours_back,
            "count":     len(messages),
            "sentiment": sentiment,
            "messages":  messages,
        }
    except FloodWaitError as e:
        return {"success": False, "error": f"Telegram rate limit — tunggu {e.seconds}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def telegram_stock_sentiment(
    ticker: str,
    chats: list[str],
    hours_back: int = 48,
    limit_per_chat: int = 100,
) -> dict:
    """
    Scan beberapa grup/channel sekaligus untuk sentimen sebuah saham.

    Args:
        ticker:         Kode saham IDX (contoh: "BBCA", "GOTO", "TLKM")
        chats:          List identifier grup/channel (username atau ID)
        hours_back:     Rentang waktu mundur dalam jam (default 48)
        limit_per_chat: Max pesan per chat (default 100)
    """
    if not _TELETHON_OK:
        return _not_available("telegram_stock_sentiment")
    if not os.path.exists(SESSION_FILE):
        return _no_session()

    all_texts = []
    chat_results = []
    errors = []

    for chat in chats:
        try:
            messages = _run(_read_messages_async(chat, limit_per_chat, ticker, hours_back))
            texts = [m["text"] for m in messages]
            all_texts.extend(texts)
            sent = _analyze_sentiment(texts)
            chat_results.append({
                "chat":      chat,
                "messages":  len(messages),
                "sentiment": sent,
                "samples":   [m["text"][:150] for m in messages[:3]],
            })
        except Exception as e:
            errors.append({"chat": chat, "error": str(e)})

    combined_sentiment = _analyze_sentiment(all_texts)

    return {
        "success":            True,
        "ticker":             ticker,
        "hours_back":         hours_back,
        "total_messages":     len(all_texts),
        "combined_sentiment": combined_sentiment,
        "per_chat":           chat_results,
        "errors":             errors,
    }


def telegram_list_chats(limit: int = 30) -> dict:
    """
    List semua grup/channel/DM Telegram yang kamu ikuti.

    Berguna untuk mencari chat identifier (username atau ID)
    yang bisa dipakai di telegram_read_messages dan telegram_stock_sentiment.
    """
    if not _TELETHON_OK:
        return _not_available("telegram_list_chats")
    if not os.path.exists(SESSION_FILE):
        return _no_session()

    try:
        chats = _run(_list_chats_async(limit))
        return {
            "success": True,
            "count":   len(chats),
            "chats":   chats,
            "tip":     "Gunakan field 'identifier' sebagai parameter 'chat' di telegram_read_messages",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def telegram_list_folders() -> dict:
    """List semua folder/filter Telegram yang sudah dibuat."""
    if not _TELETHON_OK:
        return _not_available("telegram_list_folders")
    if not os.path.exists(SESSION_FILE):
        return _no_session()
    try:
        folders = _run(_list_folders_async())
        return {"success": True, "count": len(folders), "folders": folders}
    except Exception as e:
        return {"success": False, "error": str(e)}


def telegram_read_folder(
    folder_name:    str,
    limit_per_chat: int = 50,
    hours_back:     int = 24,
    ticker_filter:  Optional[str] = None,
    save_to_db:     bool = True,
) -> dict:
    """
    Baca semua grup dalam satu folder Telegram sekaligus.

    Cocok untuk folder "CIA Member", "CIA saham", dll — semua grup di
    dalam folder dibaca sekaligus, dianalisis sentimennya, dan disimpan
    ke knowledge base lokal.

    Args:
        folder_name:    Nama folder (substring, case-insensitive). Contoh: "CIA"
        limit_per_chat: Max pesan per grup (default 50)
        hours_back:     Baca pesan N jam terakhir (default 24)
        ticker_filter:  Hanya ambil pesan yang menyebut ticker ini (optional)
        save_to_db:     Simpan ke knowledge base lokal (default True)

    Examples:
        telegram_read_folder("CIA Member")
        telegram_read_folder("CIA saham", ticker_filter="BBCA", hours_back=48)
        telegram_read_folder("CIA", hours_back=72, limit_per_chat=100)
    """
    if not _TELETHON_OK:
        return _not_available("telegram_read_folder")
    if not os.path.exists(SESSION_FILE):
        return _no_session()
    try:
        return _run(_read_folder_async(
            folder_name=folder_name,
            limit_per_chat=max(10, min(200, limit_per_chat)),
            hours_back=max(1, hours_back),
            ticker_filter=ticker_filter,
            save_to_db=save_to_db,
        ))
    except Exception as e:
        return {"success": False, "error": str(e)}


def telegram_query_knowledge(
    ticker:    Optional[str] = None,
    group:     Optional[str] = None,
    keyword:   Optional[str] = None,
    days_back: int = 7,
    limit:     int = 30,
) -> dict:
    """
    Query knowledge base Telegram yang sudah tersimpan di lokal.

    Pesan dari semua grup yang sudah pernah dibaca via telegram_read_messages
    disimpan otomatis ke database lokal dan bisa di-query kapan saja — bahkan
    tanpa koneksi Telegram aktif.

    Args:
        ticker:    Filter berdasarkan kode saham IDX yang disebut (contoh: "BBCA")
        group:     Filter berdasarkan nama grup (substring, case-insensitive)
        keyword:   Filter berdasarkan kata kunci dalam teks pesan
        days_back: Ambil data N hari ke belakang (default 7)
        limit:     Maks pesan yang dikembalikan (default 30)

    Use cases:
        - telegram_query_knowledge(ticker="BBCA") → sentimen forum tentang BBCA
        - telegram_query_knowledge(keyword="rights issue") → cari info corporate action
        - telegram_query_knowledge(keyword="bandar", days_back=3) → gossip terbaru
        - telegram_query_knowledge(group="saham", ticker="GOTO") → diskusi GOTO di grup saham
    """
    try:
        conn = _init_db()
        conditions, params = [], []

        if ticker:
            conditions.append("tickers LIKE ?")
            params.append(f"%{ticker.upper()}%")
        if group:
            conditions.append("group_name LIKE ?")
            params.append(f"%{group}%")
        if keyword:
            conditions.append("(text LIKE ? OR media_text LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if days_back:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
            conditions.append("date >= ?")
            params.append(cutoff[:10])  # YYYY-MM-DD prefix match

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur   = conn.execute(
            f"SELECT * FROM messages {where} ORDER BY date DESC LIMIT ?",
            params + [limit]
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()

        # Aggregate sentiment
        sent_labels = [r["sentiment"] for r in rows]
        bull  = sent_labels.count("bullish") + sent_labels.count("mildly bullish")
        bear  = sent_labels.count("bearish") + sent_labels.count("mildly bearish")
        total = len(sent_labels) or 1
        overall = "Bullish" if bull > bear else ("Bearish" if bear > bull else "Neutral")

        return {
            "query": {"ticker": ticker, "group": group, "keyword": keyword, "days_back": days_back},
            "count": len(rows),
            "sentiment_summary": {
                "overall":  overall,
                "bullish":  bull,
                "bearish":  bear,
                "neutral":  total - bull - bear,
                "bull_pct": round(bull / total * 100, 1),
                "bear_pct": round(bear / total * 100, 1),
            },
            "messages": rows,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def telegram_knowledge_stats() -> dict:
    """
    Statistik knowledge base Telegram lokal.

    Tampilkan berapa pesan tersimpan, dari grup apa saja, kapan terakhir diupdate.
    Berguna untuk tahu seberapa banyak konteks yang sudah dikumpulkan.
    """
    try:
        conn  = _init_db()
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        groups = conn.execute(
            "SELECT group_name, COUNT(*) as c FROM messages GROUP BY group_name ORDER BY c DESC"
        ).fetchall()
        recent = conn.execute("SELECT date FROM messages ORDER BY date DESC LIMIT 1").fetchone()
        tickers = conn.execute(
            "SELECT tickers FROM messages WHERE tickers != ''"
        ).fetchall()
        conn.close()

        # Count ticker frequency
        from collections import Counter
        tc: Counter = Counter()
        for row in tickers:
            for t in row[0].split(","):
                if t:
                    tc[t] += 1

        return {
            "total_messages": total,
            "db_path":        _DB_PATH,
            "last_updated":   recent[0] if recent else None,
            "groups":         [{"name": g[0], "messages": g[1]} for g in groups],
            "top_tickers":    [{"ticker": t, "mentions": c} for t, c in tc.most_common(15)],
        }
    except Exception as e:
        return {"error": str(e)}
