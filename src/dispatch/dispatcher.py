"""
LinkSync AI — Dispatch Orchestrator
======================================
Central dispatch controller that routes messages through
the best available channel:

1. WhatsApp Desktop (primary — native, fast)
2. WhatsApp Web (fallback — if Desktop unavailable)
3. Queue (last resort — saved for later)

Handles discovery, fallback popups, and result logging.
"""

import logging
import time
from typing import Callable, Optional

from config import (
    WHATSAPP_GROUP,
    WHATSAPP_KNOWN_PATHS,
    WHATSAPP_STORE_ID,
    WHATSAPP_DOWNLOAD_URL,
    WHATSAPP_MESSAGE_TEMPLATE,
)

logger = logging.getLogger(__name__)


def dispatch_summary(
    url: str,
    summary: str,
    group_name: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Dispatch a summary to WhatsApp using the best available method.

    Flow:
    1. Format the message
    2. Try WhatsApp Desktop
    3. If failed → try WhatsApp Web
    4. If failed → queue for later

    Args:
        url: The original URL.
        summary: The summary text.
        group_name: WhatsApp group name (default: from config/context).
        progress_callback: Optional status update callback.

    Returns:
        Dict with: success (bool), method (str), error (str|None).
    """
    group_name = group_name or _get_group_name()

    def _report(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Format the message
    message = WHATSAPP_MESSAGE_TEMPLATE.format(
        summary=summary,
        url=url,
    )

    # ── Try WhatsApp Desktop ──
    _report("Trying WhatsApp Desktop...")
    desktop_result = _try_desktop(message, group_name)
    if desktop_result:
        _report("✅ Sent via WhatsApp Desktop")
        _log_dispatch(url, summary, "sent", "desktop")
        return {"success": True, "method": "desktop", "error": None}

    # ── Try WhatsApp Web ──
    _report("Desktop unavailable. Trying WhatsApp Web...")
    web_result = _try_web(message, group_name)
    if web_result:
        _report("✅ Sent via WhatsApp Web")
        _log_dispatch(url, summary, "sent", "web")
        return {"success": True, "method": "web", "error": None}

    # ── Queue for later ──
    _report("❌ All dispatch methods failed. Queued for later.")
    _log_dispatch(url, summary, "failed", "none")
    return {
        "success": False,
        "method": "none",
        "error": "WhatsApp Desktop and Web both failed.",
    }


def dispatch_batch(
    results: list[dict],
    group_name: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> list[dict]:
    """
    Dispatch multiple summaries to WhatsApp.

    Args:
        results: List of pipeline result dicts (with 'url', 'summary', 'status').
        group_name: Target WhatsApp group.
        progress_callback: Optional callback(index, status_text).

    Returns:
        Updated results with dispatch status.
    """
    group = group_name or _get_group_name()
    dispatched_count = 0

    for i, result in enumerate(results):
        if result.get("status") != "summarized":
            continue

        url = result.get("url", "")
        summary = result.get("summary", "")

        if not summary:
            continue

        dispatch_result = dispatch_summary(url, summary, group)
        result["dispatched"] = dispatch_result["success"]
        result["dispatch_method"] = dispatch_result["method"]

        if dispatch_result["success"]:
            dispatched_count += 1

        if progress_callback:
            status = "📤 Sent" if dispatch_result["success"] else "❌ Failed"
            progress_callback(i, status)

        # Small delay between messages to avoid rate limiting
        if dispatched_count > 0:
            time.sleep(1)

    logger.info(
        "Dispatch batch complete: %d/%d sent.",
        dispatched_count,
        sum(1 for r in results if r.get("status") == "summarized"),
    )
    return results


def _try_desktop(message: str, group_name: str) -> bool:
    """Attempt to send via WhatsApp Desktop."""
    try:
        # Discover WhatsApp path
        whatsapp_path = _discover_whatsapp()
        if not whatsapp_path:
            return False

        from src.dispatch.whatsapp_desktop import send_to_group
        return send_to_group(message, group_name, whatsapp_path)
    except Exception as exc:
        logger.warning("WhatsApp Desktop dispatch error: %s", exc)
        return False


def _try_web(message: str, group_name: str) -> bool:
    """Attempt to send via WhatsApp Web."""
    try:
        from src.dispatch.whatsapp_web import send_to_group
        return send_to_group(message, group_name)
    except Exception as exc:
        logger.warning("WhatsApp Web dispatch error: %s", exc)
        return False


def _discover_whatsapp() -> Optional[str]:
    """Find WhatsApp Desktop using the app discovery system."""
    try:
        from src.discovery.app_finder import find_app
        return find_app(
            app_name="WhatsApp",
            exe_name="WhatsApp.exe",
            known_paths=WHATSAPP_KNOWN_PATHS,
            context_key="whatsapp",
        )
    except Exception as exc:
        logger.error("WhatsApp discovery failed: %s", exc)
        return None


def _get_group_name() -> str:
    """Get the WhatsApp group name from context or config."""
    try:
        from src.storage.context_manager import get_value
        return get_value("user_preferences.whatsapp_group") or WHATSAPP_GROUP
    except Exception:
        return WHATSAPP_GROUP


def _log_dispatch(url: str, summary: str, status: str, method: str) -> None:
    """Log a dispatch result to the database."""
    try:
        from src.storage.database import insert_log
        insert_log(
            url=url,
            title="",
            summary=summary,
            status=status,
            provider_used=method,
        )
    except Exception as exc:
        logger.warning("Failed to log dispatch: %s", exc)
