"""
LinkSync AI — Agent Context Manager
=====================================
Manages persistent agent state across sessions via agent_context.json.
This is the "self-healing memory" layer — the agent remembers its
configuration, user preferences, and operational state between restarts.

Context file: {PROJECT_ROOT}/agent_context.json

Stored state includes:
  • pause_state       — whether sync is paused
  • whatsapp_group    — target WhatsApp group/contact name
  • last_sync_url     — URL of the last processed page
  • last_sync_time    — ISO timestamp of last sync
  • total_syncs       — cumulative sync counter
  • hotkey            — current hotkey binding
  • user_preferences  — arbitrary user prefs dict
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import CONTEXT_FILE, WHATSAPP_GROUP, HOTKEY_DISPLAY

logger = logging.getLogger(__name__)

# Thread lock for concurrent read/write safety
_lock = threading.Lock()

# ── Default Context Schema ───────────────────────────────────
_DEFAULT_CONTEXT: dict[str, Any] = {
    "pause_state": False,
    "whatsapp_group": WHATSAPP_GROUP,
    "last_sync_url": "",
    "last_sync_time": "",
    "total_syncs": 0,
    "hotkey": HOTKEY_DISPLAY,
    "user_preferences": {},
    "version": "1.0.0",
}


# ── Core I/O ─────────────────────────────────────────────────
def _read_context_file() -> dict[str, Any]:
    """
    Read the context file from disk.
    Returns default context if the file doesn't exist or is corrupt.
    """
    context_path = Path(CONTEXT_FILE)
    if not context_path.exists():
        logger.info("Context file not found, using defaults: %s", context_path)
        return _DEFAULT_CONTEXT.copy()

    try:
        raw = context_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Context file root must be a JSON object")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Corrupt context file (%s), resetting to defaults: %s", exc, context_path
        )
        # Back up the corrupt file before overwriting
        backup_path = context_path.with_suffix(".json.bak")
        try:
            context_path.rename(backup_path)
            logger.info("Corrupt context backed up to %s", backup_path)
        except OSError:
            pass
        return _DEFAULT_CONTEXT.copy()


def _write_context_file(data: dict[str, Any]) -> None:
    """Write the context dict to disk as formatted JSON."""
    context_path = Path(CONTEXT_FILE)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ── Public API ───────────────────────────────────────────────
def load_context() -> dict[str, Any]:
    """
    Load the full agent context, merging defaults for any missing keys.
    This is the primary entry point at startup.

    Returns:
        Complete context dict with all expected keys present.
    """
    with _lock:
        stored = _read_context_file()
        # Merge defaults for any missing keys (forward-compatible)
        merged = {**_DEFAULT_CONTEXT, **stored}
        # Persist the merged version (fills in new fields from upgrades)
        if merged != stored:
            _write_context_file(merged)
            logger.info("Context file updated with new default fields")
        return merged


def save_context(context: dict[str, Any]) -> None:
    """
    Save the full agent context to disk.

    Args:
        context: The complete context dict to persist.
    """
    with _lock:
        _write_context_file(context)
    logger.debug("Context saved to %s", CONTEXT_FILE)


def get_value(key: str, default: Any = None) -> Any:
    """
    Read a single value from the context.

    Args:
        key:     The context key to read.
        default: Fallback if key is missing.

    Returns:
        The stored value, or default.
    """
    with _lock:
        ctx = _read_context_file()
    return ctx.get(key, default)


def set_value(key: str, value: Any) -> None:
    """
    Update a single value in the context and persist immediately.

    Args:
        key:   The context key to set.
        value: The value to store.
    """
    with _lock:
        ctx = _read_context_file()
        ctx[key] = value
        _write_context_file(ctx)
    logger.debug("Context key '%s' updated", key)


# ── Convenience Accessors ────────────────────────────────────
def is_paused() -> bool:
    """Check whether sync is currently paused."""
    return bool(get_value("pause_state", False))


def set_paused(paused: bool) -> None:
    """Toggle the pause state."""
    set_value("pause_state", paused)
    state_label = "PAUSED" if paused else "RESUMED"
    logger.info("Sync %s by user", state_label)


def get_whatsapp_group() -> str:
    """Return the current WhatsApp target group/contact."""
    return str(get_value("whatsapp_group", WHATSAPP_GROUP))


def set_whatsapp_group(group: str) -> None:
    """Update the WhatsApp target group/contact."""
    set_value("whatsapp_group", group)
    logger.info("WhatsApp group set to: %s", group)


def get_hotkey() -> str:
    """Return the current hotkey binding string."""
    return str(get_value("hotkey", HOTKEY_DISPLAY))


def set_hotkey(hotkey: str) -> None:
    """Update the hotkey binding."""
    set_value("hotkey", hotkey)
    logger.info("Hotkey changed to: %s", hotkey)


def record_sync(url: str) -> None:
    """
    Record that a sync cycle was completed for a URL.
    Updates last_sync_url, last_sync_time, and increments total_syncs.

    Args:
        url: The URL that was just synced.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with _lock:
        ctx = _read_context_file()
        ctx["last_sync_url"] = url
        ctx["last_sync_time"] = now
        ctx["total_syncs"] = ctx.get("total_syncs", 0) + 1
        _write_context_file(ctx)
    logger.debug("Sync recorded: %s (total: %d)", url, ctx["total_syncs"])


def get_last_sync() -> Optional[dict]:
    """
    Return info about the last sync, or None if no syncs have occurred.

    Returns:
        Dict with keys: url, time, total_syncs — or None.
    """
    ctx = load_context()
    if not ctx.get("last_sync_url"):
        return None
    return {
        "url": ctx["last_sync_url"],
        "time": ctx["last_sync_time"],
        "total_syncs": ctx["total_syncs"],
    }


# ── User Preferences ────────────────────────────────────────
def get_preference(key: str, default: Any = None) -> Any:
    """
    Read a user preference from the nested user_preferences dict.

    Args:
        key:     Preference key.
        default: Fallback value.
    """
    prefs = get_value("user_preferences", {})
    if isinstance(prefs, dict):
        return prefs.get(key, default)
    return default


def set_preference(key: str, value: Any) -> None:
    """
    Set a user preference in the nested user_preferences dict.

    Args:
        key:   Preference key.
        value: Preference value.
    """
    with _lock:
        ctx = _read_context_file()
        prefs = ctx.get("user_preferences", {})
        if not isinstance(prefs, dict):
            prefs = {}
        prefs[key] = value
        ctx["user_preferences"] = prefs
        _write_context_file(ctx)
    logger.debug("User preference '%s' updated", key)


# ── Context Reset ────────────────────────────────────────────
def reset_context() -> dict[str, Any]:
    """
    Reset the context to defaults.
    WARNING: This wipes all persisted state. Only for dev/troubleshooting.

    Returns:
        The fresh default context.
    """
    with _lock:
        fresh = _DEFAULT_CONTEXT.copy()
        _write_context_file(fresh)
    logger.warning("Agent context has been reset to defaults")
    return fresh
