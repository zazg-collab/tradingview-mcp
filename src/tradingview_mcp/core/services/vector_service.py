"""
Semantic vector search untuk knowledge base Telegram CIA.

Menggunakan:
- sentence-transformers (model paraphrase-multilingual-MiniLM-L12-v2)
  → support Bahasa Indonesia, ~470MB, gratis/lokal
- ChromaDB → vector store persistent di ~/.mcp_atila_vectors/

Flow:
  1. Saat pesan disimpan ke SQLite (telegram_service), otomatis di-embed + disimpan ke Chroma
  2. telegram_semantic_search(query) → embed query → similarity search → return relevant messages

Model diload lazy (pertama kali dipakai), sehingga startup MCP server tetap cepat.
Download model ~470MB terjadi sekali, lalu cached di ~/.cache/huggingface/
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_VECTOR_DIR  = os.path.expanduser("~/.mcp_atila_vectors")
_MODEL_NAME  = "paraphrase-multilingual-MiniLM-L12-v2"
_COLLECTION  = "cia_messages"

# Lazy-loaded singletons
_chroma_client     = None
_chroma_collection = None
_embed_model       = None

# Feature flags
_CHROMA_OK = False
_ST_OK     = False

try:
    import chromadb  # noqa: F401
    _CHROMA_OK = True
except ImportError:
    pass

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _ST_OK = True
except ImportError:
    pass

_SEMANTIC_OK = _CHROMA_OK and _ST_OK

# ── CIA vocabulary expansion ──────────────────────────────────────────────────

_CIA_VOCAB = {
    # Setup names
    r"\bkame\b": "kamehameha volume ledakan",
    r"\bkamehameha\b": "kamehameha volume ledakan breakout besar",
    r"\bsuperketat\b": "superketat semua MA rapat entry terbaik",
    r"\bketat\b": "ketat MA rapat tren mulai",
    r"\brainbow\b": "rainbow di atas semua MA no resistance",
    r"\bstar\b": "star setup premium ketat kamehameha",
    r"\bsunflower\b": "sunflower breakout gap pertama",
    r"\bara\b": "ARA auto rejection atas naik 20 persen",
    r"\barb\b": "ARB auto rejection bawah turun 20 persen",
    # Common CIA slang
    r"\bbandar\b": "bandar big player akumulasi institusi",
    r"\bbreakout\b": "breakout tembus resistance naik",
    r"\bkonsolidasi\b": "konsolidasi sideways range",
    r"\baccu\b": "akumulasi beli bertahap",
    r"\bdistri\b": "distribusi jual bertahap",
    r"\bpow\b": "power of will naik kuat",
    # Volume
    r"\bvol\b": "volume transaksi",
    r"\bv60\b": "V60 rata rata volume 60 hari",
    # TA terms
    r"\bma\b": "moving average",
    r"\brsi\b": "RSI relative strength index",
    r"\bmacd\b": "MACD momentum",
    r"\bbb\b": "bollinger bands",
    r"\bsr\b": "support resistance",
    r"\bema\b": "EMA exponential moving average",
}


def _expand_cia_query(text: str) -> str:
    """Expand CIA trading vocabulary before embedding to improve similarity scores."""
    text_lower = text.lower()
    expansions = []
    for pattern, expansion in _CIA_VOCAB.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            expansions.append(expansion)
    if expansions:
        return text + " " + " ".join(expansions)
    return text


def _get_resources():
    """Lazy-load ChromaDB + model. Thread-safe enough for single-process MCP."""
    global _chroma_client, _chroma_collection, _embed_model

    if not _SEMANTIC_OK:
        raise RuntimeError(
            "Semantic search belum tersedia.\n"
            "Install dulu:\n"
            "  cd ~/mcp-atila && venv/bin/pip install sentence-transformers chromadb"
        )

    if _chroma_collection is None:
        import chromadb
        from sentence_transformers import SentenceTransformer

        os.makedirs(_VECTOR_DIR, exist_ok=True)
        _chroma_client     = chromadb.PersistentClient(path=_VECTOR_DIR)
        _chroma_collection = _chroma_client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB loaded — %d vectors", _chroma_collection.count())

    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model '%s' …", _MODEL_NAME)
        _embed_model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model ready.")

    return _chroma_collection, _embed_model


# ── Public helpers ────────────────────────────────────────────────────────────

def is_available() -> bool:
    return _SEMANTIC_OK


def index_message(
    msg_id: str,
    text: str,
    group_name: str,
    sender: str,
    date: str,
    tickers: str,
    sentiment: str,
) -> bool:
    """
    Embed satu pesan dan simpan ke ChromaDB.
    Dipanggil dari telegram_service saat _save_message().
    Return True jika berhasil, False jika skip/error.
    """
    if not _SEMANTIC_OK:
        return False
    text = (text or "").strip()
    if len(text) < 10:        # terlalu pendek, skip
        return False

    try:
        col, model = _get_resources()

        # Cek apakah sudah ada (upsert by msg_id)
        doc_id = str(msg_id)
        embed_text = _expand_cia_query(text) if len(text) < 200 else text
        embedding = model.encode([embed_text], normalize_embeddings=True)[0].tolist()

        col.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "group":     group_name[:100],
                "sender":    (sender or "")[:50],
                "date":      (date or "")[:20],
                "tickers":   (tickers or "")[:200],
                "sentiment": (sentiment or "neutral")[:20],
            }],
        )
        return True
    except Exception as e:
        logger.warning("index_message error: %s", e)
        return False


def semantic_search(
    query: str,
    n_results: int = 10,
    group_filter: Optional[str] = None,
    sentiment_filter: Optional[str] = None,
    days_back: int = 30,
) -> dict:
    """
    Cari pesan yang secara makna mirip dengan query.

    Contoh:
        semantic_search("saham petrochemical prospek bagus")
        → akan temukan diskusi TPIA, BRPT meski tidak menyebut kata-katanya persis

        semantic_search("bandar akumulasi diam-diam")
        → temukan pesan tentang accumulation patterns

    Args:
        query:            Pertanyaan atau topik dalam bahasa bebas (Indonesia/Inggris)
        n_results:        Jumlah hasil (default 10)
        group_filter:     Filter nama grup (substring, opsional)
        sentiment_filter: Filter sentimen: "bullish", "bearish", "neutral" (opsional)
        days_back:        Cari dalam N hari terakhir (opsional, 0 = semua)

    Returns:
        dict dengan results list dan metadata pencarian
    """
    if not _SEMANTIC_OK:
        return {
            "success": False,
            "error": "Semantic search belum aktif — install sentence-transformers dan chromadb dulu.",
            "install": "cd ~/mcp-atila && venv/bin/pip install sentence-transformers chromadb",
        }

    try:
        col, model = _get_resources()

        if col.count() == 0:
            return {
                "success": False,
                "error":   "Vector store kosong. Jalankan telegram_read_folder dulu untuk index pesan.",
            }

        # Build where filter
        where_clauses = []
        if group_filter:
            # Chroma belum support LIKE, jadi skip group filter di query — filter post-hoc
            pass
        if sentiment_filter:
            where_clauses.append({"sentiment": {"$eq": sentiment_filter.lower()}})

        where = where_clauses[0] if len(where_clauses) == 1 else (
            {"$and": where_clauses} if len(where_clauses) > 1 else None
        )

        # Embed query (with CIA vocab expansion)
        expanded_query = _expand_cia_query(query)
        q_embedding = model.encode([expanded_query], normalize_embeddings=True)[0].tolist()

        # Query ChromaDB
        kwargs = dict(
            query_embeddings=[q_embedding],
            n_results=min(n_results * 3, col.count()),   # over-fetch for post-filter
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        distances = results["distances"][0]

        # Post-filter: date range
        from datetime import datetime, timezone, timedelta
        if days_back > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        else:
            cutoff = "0000-00-00"

        # Post-filter: group substring
        hits = []
        for doc, meta, dist in zip(docs, metas, distances):
            if meta.get("date", "") < cutoff:
                continue
            if group_filter and group_filter.lower() not in meta.get("group", "").lower():
                continue
            similarity = round(1 - dist, 3)   # cosine distance → similarity
            hits.append({
                "text":       doc,
                "similarity": similarity,
                "group":      meta.get("group", ""),
                "sender":     meta.get("sender", ""),
                "date":       meta.get("date", ""),
                "tickers":    meta.get("tickers", "").split(",") if meta.get("tickers") else [],
                "sentiment":  meta.get("sentiment", "neutral"),
            })

        # Sort by similarity descending, cap at n_results
        hits.sort(key=lambda x: x["similarity"], reverse=True)
        hits = hits[:n_results]

        # Aggregate tickers from results
        from collections import Counter
        ticker_counter: Counter = Counter()
        for h in hits:
            for t in h["tickers"]:
                t = t.strip()
                if t:
                    ticker_counter[t] += 1

        return {
            "success":        True,
            "query":          query,
            "query_expanded": expanded_query if expanded_query != query else None,
            "total_vectors":  col.count(),
            "results_found": len(hits),
            "top_tickers":  [{"ticker": t, "mentions": c} for t, c in ticker_counter.most_common(10)],
            "results":      hits,
        }

    except Exception as e:
        logger.error("semantic_search error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def vector_stats() -> dict:
    """Statistik vector store."""
    if not _SEMANTIC_OK:
        return {
            "available": False,
            "reason":    "sentence-transformers atau chromadb belum terinstall",
            "install":   "cd ~/mcp-atila && venv/bin/pip install sentence-transformers chromadb",
        }
    try:
        col, _ = _get_resources()
        return {
            "available":     True,
            "total_vectors": col.count(),
            "vector_dir":    _VECTOR_DIR,
            "model":         _MODEL_NAME,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}
