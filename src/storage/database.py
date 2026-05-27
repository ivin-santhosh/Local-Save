"""
LinkSync AI — SQLite Database Layer
====================================
Persistent storage for all sync operations. Stores every URL capture,
summary, dispatch status, and feedback state.

Table: sync_logs
    id           INTEGER PRIMARY KEY
    url          TEXT NOT NULL
    title        TEXT
    summary      TEXT
    status       TEXT (sent | failed | skipped | irrelevant | pending)
    dispatched_at TEXT (ISO 8601 timestamp, nullable)
    created_at   TEXT (ISO 8601 timestamp, auto-filled)

Thread-safe — uses WAL journal mode and check_same_thread=False.
"""

import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import DB_PATH

logger = logging.getLogger(__name__)

# ── Schema ───────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sync_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT    NOT NULL,
    title         TEXT    DEFAULT '',
    summary       TEXT    DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('sent','failed','skipped','irrelevant','pending')),
    dispatched_at TEXT,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_sync_logs_url       ON sync_logs(url);
CREATE INDEX IF NOT EXISTS idx_sync_logs_status    ON sync_logs(status);
CREATE INDEX IF NOT EXISTS idx_sync_logs_created   ON sync_logs(created_at);
"""

# Migration: add columns that may not exist yet (forward-compatible)
_MIGRATIONS = [
    ("dispatched_at", "ALTER TABLE sync_logs ADD COLUMN dispatched_at TEXT;"),
]


# ── Connection Pool ──────────────────────────────────────────
_conn: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """Return a module-level SQLite connection, creating it on first call."""
    global _conn
    if _conn is None:
        # Ensure the parent directory exists
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=False,
            timeout=10.0,
        )
        _conn.row_factory = sqlite3.Row
        # Performance tuning
        _conn.execute("PRAGMA journal_mode = WAL;")
        _conn.execute("PRAGMA synchronous = NORMAL;")
        _conn.execute("PRAGMA foreign_keys = ON;")
        logger.info("SQLite connection opened: %s", DB_PATH)
    return _conn


# ── Initialization ───────────────────────────────────────────
def init_db() -> None:
    """
    Create tables, indexes, and run any pending schema migrations.
    Safe to call multiple times (idempotent).
    """
    conn = _get_connection()
    cursor = conn.cursor()

    # Create core table
    cursor.executescript(_CREATE_TABLE_SQL)
    cursor.executescript(_CREATE_INDEX_SQL)

    # Run forward-compatible migrations
    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(sync_logs);").fetchall()
    }
    for col_name, alter_sql in _MIGRATIONS:
        if col_name not in existing_columns:
            try:
                cursor.execute(alter_sql)
                logger.info("Migration applied: added column '%s'", col_name)
            except sqlite3.OperationalError:
                # Column already exists (race condition guard)
                pass

    conn.commit()
    logger.info("Database initialized at %s", DB_PATH)


# ── CRUD Operations ──────────────────────────────────────────
def insert_log(
    url: str,
    title: str = "",
    summary: str = "",
    status: str = "pending",
) -> int:
    """
    Insert a new sync log entry.

    Args:
        url:     The captured URL.
        title:   Page title extracted by the scraper.
        summary: LLM-generated summary (may be empty initially).
        status:  One of 'sent', 'failed', 'skipped', 'irrelevant', 'pending'.

    Returns:
        The auto-generated row ID.
    """
    conn = _get_connection()
    cursor = conn.execute(
        """
        INSERT INTO sync_logs (url, title, summary, status)
        VALUES (?, ?, ?, ?)
        """,
        (url, title, summary, status),
    )
    conn.commit()
    log_id = cursor.lastrowid
    logger.debug("Inserted sync_log id=%d url=%s status=%s", log_id, url, status)
    return log_id


def update_log(
    log_id: int,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[str] = None,
    dispatched_at: Optional[str] = None,
) -> None:
    """
    Update an existing log entry. Only non-None fields are updated.
    """
    fields = []
    values = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if summary is not None:
        fields.append("summary = ?")
        values.append(summary)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if dispatched_at is not None:
        fields.append("dispatched_at = ?")
        values.append(dispatched_at)

    if not fields:
        return

    values.append(log_id)
    sql = f"UPDATE sync_logs SET {', '.join(fields)} WHERE id = ?"
    conn = _get_connection()
    conn.execute(sql, values)
    conn.commit()
    logger.debug("Updated sync_log id=%d fields=%s", log_id, fields)


def mark_dispatched(log_id: int) -> None:
    """Mark a log entry as successfully dispatched with current timestamp."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    update_log(log_id, status="sent", dispatched_at=now)


def mark_failed(log_id: int) -> None:
    """Mark a log entry as failed dispatch."""
    update_log(log_id, status="failed")


def mark_irrelevant(log_id: int) -> None:
    """Mark a log entry as irrelevant (user feedback via Logs UI)."""
    update_log(log_id, status="irrelevant")
    logger.info("Log id=%d marked as irrelevant", log_id)


# ── Query Operations ─────────────────────────────────────────
def get_recent_logs(limit: int = 50) -> list[dict]:
    """
    Retrieve the most recent sync log entries.

    Args:
        limit: Maximum number of entries to return (default 50).

    Returns:
        List of dicts with keys: id, url, title, summary, status,
        dispatched_at, created_at.
    """
    conn = _get_connection()
    rows = conn.execute(
        """
        SELECT id, url, title, summary, status, dispatched_at, created_at
        FROM sync_logs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_log_by_id(log_id: int) -> Optional[dict]:
    """Retrieve a single log entry by ID."""
    conn = _get_connection()
    row = conn.execute(
        """
        SELECT id, url, title, summary, status, dispatched_at, created_at
        FROM sync_logs
        WHERE id = ?
        """,
        (log_id,),
    ).fetchone()
    return dict(row) if row else None


def is_url_processed(url: str, hours: int = 24) -> bool:
    """
    Check if a URL was already processed within the last N hours.
    Used for deduplication before starting a new sync cycle.

    Args:
        url:   The URL to check.
        hours: Look-back window (default 24 hours).

    Returns:
        True if the URL has a non-skipped entry within the window.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    conn = _get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM sync_logs
        WHERE url = ?
          AND status NOT IN ('skipped', 'failed')
          AND created_at >= ?
        """,
        (url, cutoff),
    ).fetchone()
    return row["cnt"] > 0


def get_irrelevant_urls() -> list[str]:
    """Return all URLs that have been marked irrelevant (for negative filter seeding)."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT DISTINCT url FROM sync_logs WHERE status = 'irrelevant'"
    ).fetchall()
    return [row["url"] for row in rows]


def get_stats() -> dict:
    """
    Return aggregate statistics about sync activity.

    Returns:
        Dict with keys: total, sent, failed, skipped, irrelevant, pending.
    """
    conn = _get_connection()
    row = conn.execute(
        """
        SELECT
            COUNT(*)                                     AS total,
            SUM(CASE WHEN status = 'sent'       THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status = 'skipped'    THEN 1 ELSE 0 END) AS skipped,
            SUM(CASE WHEN status = 'irrelevant' THEN 1 ELSE 0 END) AS irrelevant,
            SUM(CASE WHEN status = 'pending'    THEN 1 ELSE 0 END) AS pending
        FROM sync_logs
        """
    ).fetchone()
    return dict(row)


# ── Cleanup ──────────────────────────────────────────────────
def purge_old_logs(days: int = 30) -> int:
    """
    Delete log entries older than N days to keep the database lean.

    Args:
        days: Entries older than this many days are deleted (default 30).

    Returns:
        Number of rows deleted.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    conn = _get_connection()
    cursor = conn.execute(
        "DELETE FROM sync_logs WHERE created_at < ?",
        (cutoff,),
    )
    conn.commit()
    deleted = cursor.rowcount
    if deleted > 0:
        logger.info("Purged %d log entries older than %d days", deleted, days)
    return deleted


def close_db() -> None:
    """Close the database connection. Call on application shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
        logger.info("SQLite connection closed")
