"""
LinkSync AI — Node B: The Filter
==================================
The second node in the LangGraph pipeline. Responsible for
scraping the page content and determining the summarization
strategy based on content length:

  < 5k chars  → 2-3 line summary
  5k-20k      → 4-6 lines
  20k-50k     → 7-10 lines
  > 50k       → Title-only mode (skip full summarization)

Usage (called by graph.py — not directly):
    result = filter_node(state)
"""

import logging
from config import CONTENT_LENGTH_THRESHOLD, SUMMARY_LENGTH_TIERS

logger = logging.getLogger(__name__)


def filter_node(state: dict) -> dict:
    """
    Scrape the page and determine summarization strategy.

    Fetches the page content via Playwright, checks its length,
    and decides how many lines the summary should be.

    Args:
        state: LangGraph state dict containing at least 'url'.

    Returns:
        Updated state with:
        - content (str): Page body text
        - title_only (bool): True if content is too long for full summary
        - page_title (str): The HTML <title> of the page
        - content_length (int): Character count of body text
        - summary_max_lines (int): Max lines for the summary
    """
    url = state.get("url", "").strip()
    logger.info("Filter node scraping: %s", url)

    # ── Handle empty URLs (UIA tabs without URL) ──
    if not url:
        logger.info("No URL available — using title-only mode.")
        return {
            **state,
            "content": "",
            "title_only": True,
            "page_title": state.get("title", "Unknown"),
            "content_length": 0,
            "summary_max_lines": 2,
        }

    # ── Scrape the page ──
    try:
        from src.scraper.page_scraper import scrape_page
        page_data = scrape_page(url)
    except Exception as exc:
        logger.error("Scraping failed for %s: %s", url, exc)
        return {
            **state,
            "content": "",
            "title_only": True,
            "page_title": state.get("title", "Unknown"),
            "content_length": 0,
            "summary_max_lines": 3,
            "error": f"Scraping failed: {exc}",
        }

    if page_data.get("error"):
        logger.warning("Scraper returned error: %s", page_data["error"])
        return {
            **state,
            "content": "",
            "title_only": True,
            "page_title": page_data.get("title", state.get("title", "")),
            "content_length": 0,
            "summary_max_lines": 3,
            "error": page_data["error"],
        }

    content = page_data.get("content", "")
    page_title = page_data.get("title", "")
    content_length = len(content)

    logger.info(
        "Page scraped: title='%s', length=%d chars",
        page_title[:50], content_length,
    )

    # ── Determine summarization strategy ──
    title_only = content_length > CONTENT_LENGTH_THRESHOLD
    summary_max_lines = _determine_max_lines(content_length)

    if title_only:
        logger.info(
            "Content too long (%d chars > %d threshold). Title-only mode.",
            content_length, CONTENT_LENGTH_THRESHOLD,
        )

    return {
        **state,
        "content": content if not title_only else "",
        "title_only": title_only,
        "page_title": page_title,
        "content_length": content_length,
        "summary_max_lines": summary_max_lines,
    }


def _determine_max_lines(content_length: int) -> int:
    """
    Determine the maximum number of summary lines based on content depth.

    Uses SUMMARY_LENGTH_TIERS from config:
      < 5k chars  → 3 lines
      5k-20k      → 6 lines
      20k-50k     → 10 lines

    Args:
        content_length: Number of characters in the page body.

    Returns:
        Maximum number of lines for the summary.
    """
    max_lines = 3  # Default for very short content
    for threshold, lines in SUMMARY_LENGTH_TIERS:
        if content_length <= threshold:
            return lines
        max_lines = lines
    return max_lines
