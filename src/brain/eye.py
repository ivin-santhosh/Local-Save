"""
LinkSync AI — Node A: The Eye
================================
The first node in the LangGraph pipeline. Responsible for
validating a URL before any heavy processing happens:

1. Blacklist check — is this a private/sensitive domain?
2. Dedup check — was this URL already processed recently?
3. Negative filter — is this similar to content the user rejected?

If any check fails, the pipeline aborts immediately.

Usage (called by graph.py — not directly):
    result = eye_node(state)
"""

import logging
from urllib.parse import urlparse

from config import BLACKLISTED_DOMAINS

logger = logging.getLogger(__name__)


def eye_node(state: dict) -> dict:
    """
    Validate a URL against privacy blacklist, duplicates,
    and the user's negative feedback filter.

    Args:
        state: LangGraph state dict containing at least 'url'.

    Returns:
        Updated state dict with validation results:
        - abort (bool): True if the URL should be skipped
        - abort_reason (str|None): Why it was skipped
        - duplicate (bool): True if recently processed
        - negative_match (bool): True if similar to rejected content
    """
    url = state.get("url", "")
    title = state.get("title", "")

    logger.info("Eye examining: %s", url)

    # ── Blacklist Check ──
    if _is_blacklisted(url):
        reason = f"Domain is blacklisted (privacy protection)"
        logger.info("ABORT — %s: %s", reason, url)
        return {
            **state,
            "abort": True,
            "abort_reason": reason,
            "duplicate": False,
            "negative_match": False,
        }

    # ── Dedup Check ──
    try:
        from src.storage.database import is_url_processed
        if is_url_processed(url):
            logger.info("SKIP — URL already processed recently: %s", url)
            return {
                **state,
                "abort": True,
                "abort_reason": "Already processed in the last 24 hours",
                "duplicate": True,
                "negative_match": False,
            }
    except Exception as exc:
        logger.warning("Dedup check failed (continuing): %s", exc)

    # ── Negative Filter Check ──
    try:
        from src.storage.vector_store import is_similar_to_negative
        # Use the title as a proxy for content similarity
        check_text = title if title else url
        if is_similar_to_negative(check_text):
            logger.info(
                "SKIP — Similar to user-rejected content: %s", url
            )
            return {
                **state,
                "abort": True,
                "abort_reason": "Similar to content marked as irrelevant",
                "duplicate": False,
                "negative_match": True,
            }
    except Exception as exc:
        logger.warning("Negative filter check failed (continuing): %s", exc)

    # ── All clear ──
    logger.info("Eye approved: %s", url)
    return {
        **state,
        "abort": False,
        "abort_reason": None,
        "duplicate": False,
        "negative_match": False,
    }


def _is_blacklisted(url: str) -> bool:
    """
    Check if a URL belongs to a blacklisted domain.

    Uses substring matching against BLACKLISTED_DOMAINS from config.
    This catches both exact domains and domain patterns like 'banking'.

    Args:
        url: The URL to check.

    Returns:
        True if the URL matches any blacklisted pattern.
    """
    if not url:
        return False

    # Check for protocol-level blacklists (chrome://, about:, etc.)
    for pattern in BLACKLISTED_DOMAINS:
        if "://" in pattern and url.startswith(pattern):
            return True

    # Check domain-level blacklists
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        full_url_lower = url.lower()

        for pattern in BLACKLISTED_DOMAINS:
            if "://" in pattern:
                continue  # Already handled above
            pattern_lower = pattern.lower()
            if pattern_lower in domain or pattern_lower in full_url_lower:
                return True
    except Exception:
        pass

    return False
