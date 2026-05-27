"""
LinkSync AI — Playwright Page Scraper
=======================================
Headless Chromium scraper that fetches page content for
summarization. This is a SEPARATE browser instance from the
user's actual browser — it's invisible and used only for
content extraction.

Uses a singleton pattern: one browser instance is shared
across all scrape calls for efficiency.

Usage:
    from src.scraper.page_scraper import scrape_page
    data = scrape_page("https://example.com")
    # data = {"title": "...", "content": "...", "content_length": 1234}
"""

import asyncio
import logging
import threading
from typing import Optional

from config import SCRAPER_TIMEOUT, SCRAPER_WAIT_UNTIL

logger = logging.getLogger(__name__)

# Singleton browser state
_browser = None
_context = None
_playwright = None
_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None


async def _ensure_browser():
    """
    Lazily create the headless Chromium browser if not already running.

    Uses Playwright's async API. The browser instance is reused
    across all scrape calls for performance.
    """
    global _browser, _context, _playwright

    if _browser is not None:
        return

    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)
    _context = await _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 720},
    )
    logger.info("Playwright headless browser started.")


async def _scrape_page_async(url: str) -> dict:
    """
    Internal async implementation of page scraping.

    Navigates to the URL, waits for content to load, then
    extracts the page title and body text.

    Args:
        url: The URL to scrape.

    Returns:
        Dict with keys: title, content, content_length, error.
    """
    await _ensure_browser()

    page = None
    try:
        page = await _context.new_page()

        # Navigate with timeout
        await page.goto(
            url,
            wait_until=SCRAPER_WAIT_UNTIL,
            timeout=SCRAPER_TIMEOUT,
        )

        # Extract title
        title = await page.title()

        # Extract body text (strips all HTML, keeps readable text)
        content = await page.inner_text("body")

        # Clean up excessive whitespace
        content = "\n".join(
            line.strip() for line in content.split("\n")
            if line.strip()
        )

        logger.info(
            "Scraped: title='%s' (%d chars)",
            title[:50], len(content),
        )

        return {
            "title": title,
            "content": content,
            "content_length": len(content),
            "error": None,
        }

    except Exception as exc:
        logger.error("Scrape error for %s: %s", url, exc)
        return {
            "title": "",
            "content": "",
            "content_length": 0,
            "error": str(exc),
        }

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def _close_browser_async():
    """Internal async implementation of browser cleanup."""
    global _browser, _context, _playwright

    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright browser closed.")


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """
    Get or create an event loop for running async Playwright code.

    Handles the common issue of 'no running event loop' in threaded
    contexts by creating a dedicated loop.

    Returns:
        An asyncio event loop.
    """
    global _loop

    if _loop is not None and not _loop.is_closed():
        return _loop

    _loop = asyncio.new_event_loop()
    return _loop


def scrape_page(url: str) -> dict:
    """
    Scrape a web page and extract its title and body text.

    This is the synchronous wrapper around the async Playwright
    scraper. It manages the event loop automatically.

    Args:
        url: The URL to scrape.

    Returns:
        Dict with keys:
        - title (str): HTML page title
        - content (str): Full body text (cleaned)
        - content_length (int): Character count
        - error (str|None): Error message if scraping failed
    """
    with _lock:
        loop = _get_or_create_loop()
        try:
            return loop.run_until_complete(_scrape_page_async(url))
        except RuntimeError as exc:
            if "This event loop is already running" in str(exc):
                # We're inside an existing async context — use nest_asyncio
                try:
                    import nest_asyncio
                    nest_asyncio.apply(loop)
                    return loop.run_until_complete(_scrape_page_async(url))
                except ImportError:
                    logger.error(
                        "Cannot run async scraper in existing event loop. "
                        "Install nest_asyncio: pip install nest_asyncio"
                    )
                    return {
                        "title": "",
                        "content": "",
                        "content_length": 0,
                        "error": str(exc),
                    }
            raise


def close_browser() -> None:
    """
    Close the Playwright browser and release resources.

    Called during application shutdown.
    """
    with _lock:
        loop = _get_or_create_loop()
        try:
            loop.run_until_complete(_close_browser_async())
        except Exception as exc:
            logger.debug("Error closing browser: %s", exc)
