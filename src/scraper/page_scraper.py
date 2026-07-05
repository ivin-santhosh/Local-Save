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
_loop_thread: Optional[threading.Thread] = None
_launching = False


def _start_loop_thread():
    """Start a dedicated background thread for running async scraping coroutines."""
    global _loop, _loop_thread
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        _loop_thread = threading.Thread(target=run_loop, args=(_loop,), daemon=True)
        _loop_thread.start()
        logger.debug("Scraper background event loop started.")


async def _ensure_browser():
    """
    Lazily create the headless Chromium browser if not already running.

    Uses Playwright's async API. The browser instance is reused
    across all scrape calls for performance.
    """
    global _browser, _context, _playwright, _launching

    if _browser is not None:
        return

    # Wait if another worker is already launching it
    while _launching:
        await asyncio.sleep(0.1)
        if _browser is not None:
            return

    _launching = True
    try:
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
    finally:
        _launching = False


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


def scrape_page(url: str) -> dict:
    """
    Scrape a web page and extract its title and body text.

    Submits the scraping coroutine to the background async event loop
    so that multiple threads can scrape concurrently.

    Args:
        url: The URL to scrape.

    Returns:
        Dict with title, content, content_length, and error keys.
    """
    with _lock:
        _start_loop_thread()

    future = asyncio.run_coroutine_threadsafe(_scrape_page_async(url), _loop)
    try:
        return future.result(timeout=SCRAPER_TIMEOUT / 1000 + 5.0)
    except Exception as exc:
        logger.error("Scraping thread future timed out or failed: %s", exc)
        return {
            "title": "",
            "content": "",
            "content_length": 0,
            "error": str(exc),
        }


def close_browser() -> None:
    """
    Close the Playwright browser and stop the background event loop thread.
    """
    global _loop, _loop_thread
    with _lock:
        if _loop is not None and not _loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(_close_browser_async(), _loop)
            try:
                future.result(timeout=10)
            except Exception:
                pass
            _loop.call_soon_threadsafe(_loop.stop)
            if _loop_thread:
                _loop_thread.join(timeout=5)
                _loop_thread = None
            _loop = None
