"""
LinkSync AI — Storage Module: SQLite, ChromaDB, and agent context.

Submodules:
    database        — SQLite sync log persistence
    vector_store    — ChromaDB semantic embeddings & negative filter
    context_manager — JSON-based agent state across sessions
"""

from src.storage.database import (
    init_db,
    insert_log,
    update_log,
    mark_dispatched,
    mark_failed,
    mark_irrelevant,
    get_recent_logs,
    get_log_by_id,
    is_url_processed,
    get_irrelevant_urls,
    get_stats,
    purge_old_logs,
    close_db,
)
from src.storage.vector_store import (
    init_vector_store,
    add_article,
    is_duplicate,
    query_similar_articles,
    add_to_negative_filter,
    is_similar_to_negative,
    remove_from_negative_filter,
    get_collection_stats,
)
from src.storage.context_manager import (
    load_context,
    save_context,
    get_value,
    set_value,
    is_paused,
    set_paused,
    get_whatsapp_group,
    set_whatsapp_group,
    record_sync,
    get_last_sync,
)

__all__ = [
    # database
    "init_db",
    "insert_log",
    "update_log",
    "mark_dispatched",
    "mark_failed",
    "mark_irrelevant",
    "get_recent_logs",
    "get_log_by_id",
    "is_url_processed",
    "get_irrelevant_urls",
    "get_stats",
    "purge_old_logs",
    "close_db",
    # vector_store
    "init_vector_store",
    "add_article",
    "is_duplicate",
    "query_similar_articles",
    "add_to_negative_filter",
    "is_similar_to_negative",
    "remove_from_negative_filter",
    "get_collection_stats",
    # context_manager
    "load_context",
    "save_context",
    "get_value",
    "set_value",
    "is_paused",
    "set_paused",
    "get_whatsapp_group",
    "set_whatsapp_group",
    "record_sync",
    "get_last_sync",
]
