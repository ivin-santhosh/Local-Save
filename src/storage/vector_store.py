"""
LinkSync AI — ChromaDB Vector Store
=====================================
Semantic memory layer using ChromaDB for:
  1. Article deduplication (by URL + embedding similarity)
  2. Negative filtering (suppress articles similar to user-rejected ones)

Collections:
  • article_embeddings — every successfully processed article
  • negative_filter    — embeddings of URLs the user marked "Irrelevant"

Uses ChromaDB's built-in all-MiniLM-L6-v2 sentence-transformer embeddings,
so no external API or GPU is required.
"""

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings

from config import CHROMA_PATH, NEGATIVE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

# ── Module-level Singleton ───────────────────────────────────
_client: Optional[chromadb.ClientAPI] = None
_article_collection: Optional[chromadb.Collection] = None
_negative_collection: Optional[chromadb.Collection] = None


def _get_client() -> chromadb.ClientAPI:
    """Return a persistent ChromaDB client, creating it on first call."""
    global _client
    if _client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False,
            ),
        )
        logger.info("ChromaDB client initialized at %s", CHROMA_PATH)
    return _client


def _get_article_collection() -> chromadb.Collection:
    """Get or create the article_embeddings collection."""
    global _article_collection
    if _article_collection is None:
        client = _get_client()
        _article_collection = client.get_or_create_collection(
            name="article_embeddings",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection 'article_embeddings' ready (count=%d)",
            _article_collection.count(),
        )
    return _article_collection


def _get_negative_collection() -> chromadb.Collection:
    """Get or create the negative_filter collection."""
    global _negative_collection
    if _negative_collection is None:
        client = _get_client()
        _negative_collection = client.get_or_create_collection(
            name="negative_filter",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection 'negative_filter' ready (count=%d)",
            _negative_collection.count(),
        )
    return _negative_collection


# ── Initialization ───────────────────────────────────────────
def init_vector_store() -> None:
    """
    Eagerly initialize the ChromaDB client and both collections.
    Safe to call multiple times (idempotent).
    """
    _get_article_collection()
    _get_negative_collection()
    logger.info("Vector store fully initialized")


# ── Article Embeddings ───────────────────────────────────────
def add_article(
    url: str,
    summary: str,
    metadata: Optional[dict] = None,
) -> None:
    """
    Store an article's summary embedding in the article_embeddings collection.

    Args:
        url:      The article URL (used as the unique document ID).
        summary:  The LLM-generated summary text to embed.
        metadata: Optional dict of extra metadata (title, domain, etc.).
    """
    collection = _get_article_collection()

    doc_metadata = {"url": url}
    if metadata:
        doc_metadata.update(metadata)

    # Upsert to handle re-processing gracefully
    collection.upsert(
        ids=[_url_to_id(url)],
        documents=[summary],
        metadatas=[doc_metadata],
    )
    logger.debug("Upserted article embedding for %s", url)


def is_duplicate(url: str) -> bool:
    """
    Check if a URL has already been embedded in the article collection.

    Args:
        url: The URL to check.

    Returns:
        True if the URL already exists in article_embeddings.
    """
    collection = _get_article_collection()
    doc_id = _url_to_id(url)
    try:
        result = collection.get(ids=[doc_id])
        return len(result["ids"]) > 0
    except Exception:
        return False


def query_similar_articles(
    text: str,
    n_results: int = 5,
) -> list[dict]:
    """
    Find articles semantically similar to the given text.

    Args:
        text:      Query text (e.g., a new summary to compare).
        n_results: Max number of results to return.

    Returns:
        List of dicts with keys: id, url, document, distance.
    """
    collection = _get_article_collection()
    if collection.count() == 0:
        return []

    # Clamp n_results to collection size
    actual_n = min(n_results, collection.count())

    results = collection.query(
        query_texts=[text],
        n_results=actual_n,
        include=["documents", "metadatas", "distances"],
    )

    items = []
    for i in range(len(results["ids"][0])):
        items.append(
            {
                "id": results["ids"][0][i],
                "url": results["metadatas"][0][i].get("url", ""),
                "document": results["documents"][0][i],
                "distance": results["distances"][0][i],
            }
        )
    return items


# ── Negative Filter ──────────────────────────────────────────
def add_to_negative_filter(url: str, summary: str) -> None:
    """
    Add a URL + summary to the negative filter collection.
    Future articles with similar embeddings will be flagged for suppression.

    Args:
        url:     The rejected article's URL.
        summary: The rejected article's summary text to embed.
    """
    collection = _get_negative_collection()
    collection.upsert(
        ids=[_url_to_id(url)],
        documents=[summary],
        metadatas=[{"url": url}],
    )
    logger.info("Added to negative filter: %s", url)


def is_similar_to_negative(
    summary: str,
    threshold: Optional[float] = None,
) -> bool:
    """
    Check if a summary is semantically similar to any entry in the
    negative filter (i.e., the user previously marked similar content
    as irrelevant).

    ChromaDB returns *cosine distance* (0 = identical, 2 = opposite).
    Cosine similarity = 1 - distance.
    We flag if similarity ≥ threshold.

    Args:
        summary:   The summary text to check.
        threshold: Cosine similarity threshold (default from config:
                   NEGATIVE_SIMILARITY_THRESHOLD = 0.85).

    Returns:
        True if any negative-filter entry has similarity ≥ threshold.
    """
    if threshold is None:
        threshold = NEGATIVE_SIMILARITY_THRESHOLD

    collection = _get_negative_collection()
    if collection.count() == 0:
        return False

    results = collection.query(
        query_texts=[summary],
        n_results=1,
        include=["distances"],
    )

    if not results["distances"] or not results["distances"][0]:
        return False

    # ChromaDB cosine distance → similarity
    distance = results["distances"][0][0]
    similarity = 1.0 - distance

    if similarity >= threshold:
        logger.info(
            "Summary flagged by negative filter (similarity=%.3f, threshold=%.3f)",
            similarity,
            threshold,
        )
        return True

    return False


def remove_from_negative_filter(url: str) -> None:
    """Remove a URL from the negative filter (undo 'mark irrelevant')."""
    collection = _get_negative_collection()
    doc_id = _url_to_id(url)
    try:
        collection.delete(ids=[doc_id])
        logger.info("Removed from negative filter: %s", url)
    except Exception:
        logger.warning("URL not found in negative filter: %s", url)


# ── Collection Statistics ────────────────────────────────────
def get_collection_stats() -> dict:
    """
    Return counts for both collections.

    Returns:
        Dict with keys: article_count, negative_count.
    """
    return {
        "article_count": _get_article_collection().count(),
        "negative_count": _get_negative_collection().count(),
    }


# ── Helpers ──────────────────────────────────────────────────
def _url_to_id(url: str) -> str:
    """
    Convert a URL to a stable ChromaDB document ID.
    ChromaDB IDs must be non-empty strings. We use a hash to avoid
    issues with very long URLs or special characters.
    """
    import hashlib

    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def reset_collections() -> None:
    """
    Delete and recreate both collections.
    WARNING: This destroys all stored embeddings. Only for dev/testing.
    """
    global _article_collection, _negative_collection
    client = _get_client()

    for name in ("article_embeddings", "negative_filter"):
        try:
            client.delete_collection(name)
            logger.warning("Deleted collection '%s'", name)
        except ValueError:
            pass  # Collection didn't exist

    _article_collection = None
    _negative_collection = None
    init_vector_store()
    logger.warning("All vector collections have been reset")
