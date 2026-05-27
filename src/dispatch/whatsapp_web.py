"""
LinkSync AI — WhatsApp Web Fallback
=====================================
Playwright-based WhatsApp Web automation. Used when
WhatsApp Desktop is not available.

Uses a persistent browser context so the user only needs
to scan the QR code once — login is preserved across sessions.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from config import PROJECT_ROOT, WHATSAPP_GROUP

logger = logging.getLogger(__name__)

_WHATSAPP_WEB_URL = "https://web.whatsapp.com"
_CONTEXT_DIR = PROJECT_ROOT / "data" / "whatsapp_web_context"
_browser = None
_context = None
_page = None


async def _launch_async() -> bool:
    """Launch WhatsApp Web in a persistent Playwright context."""
    global _browser, _context, _page

    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=False)  # Must be visible for QR
        _context = await _browser.new_context(
            storage_state=str(_CONTEXT_DIR / "state.json")
            if (_CONTEXT_DIR / "state.json").exists() else None,
        )
        _page = await _context.new_page()
        await _page.goto(_WHATSAPP_WEB_URL, wait_until="domcontentloaded")

        logger.info("WhatsApp Web opened.")
        return True
    except Exception as exc:
        logger.error("Failed to launch WhatsApp Web: %s", exc)
        return False


async def _is_logged_in_async() -> bool:
    """Check if the user is logged into WhatsApp Web."""
    if not _page:
        return False
    try:
        await _page.wait_for_selector('[data-testid="chat-list"]', timeout=10000)
        return True
    except Exception:
        return False


async def _save_session_async() -> None:
    """Save the browser session for reuse."""
    if _context:
        _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        state = await _context.storage_state()
        import json
        with open(_CONTEXT_DIR / "state.json", "w") as f:
            json.dump(state, f)
        logger.info("WhatsApp Web session saved.")


async def _find_group_async(group_name: str) -> bool:
    """Navigate to a WhatsApp group."""
    if not _page:
        return False
    try:
        # Click search
        search = await _page.wait_for_selector(
            '[data-testid="chat-list-search"],'
            '[title="Search input textbox"],'
            '[contenteditable="true"]',
            timeout=5000,
        )
        if search:
            await search.click()
            await search.fill(group_name)
            await _page.wait_for_timeout(2000)

            # Click the first matching result
            result = await _page.query_selector(
                f'span[title*="{group_name}"]'
            )
            if result:
                await result.click()
                await _page.wait_for_timeout(1000)
                logger.info("Opened group: %s", group_name)
                return True

        return False
    except Exception as exc:
        logger.error("Failed to find group: %s", exc)
        return False


async def _send_message_async(text: str) -> bool:
    """Send a message in the current chat."""
    if not _page:
        return False
    try:
        # Find message input
        msg_box = await _page.wait_for_selector(
            '[data-testid="conversation-compose-box-input"],'
            '[contenteditable="true"][data-tab="10"]',
            timeout=5000,
        )
        if not msg_box:
            return False

        await msg_box.click()

        # Type message (handle newlines)
        for line in text.split("\n"):
            await _page.keyboard.type(line)
            await _page.keyboard.press("Shift+Enter")

        await _page.keyboard.press("Enter")
        await _page.wait_for_timeout(1000)

        # Save session after successful send
        await _save_session_async()

        logger.info("Message sent via WhatsApp Web.")
        return True
    except Exception as exc:
        logger.error("Failed to send via Web: %s", exc)
        return False


async def _close_async() -> None:
    """Close the WhatsApp Web browser."""
    global _browser, _context, _page
    if _context:
        await _save_session_async()
    if _page:
        await _page.close()
        _page = None
    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None


# ============================================================
# Synchronous Wrappers
# ============================================================

def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=60)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def launch() -> bool:
    """Launch WhatsApp Web. Returns True if opened."""
    return _run_async(_launch_async())


def is_logged_in() -> bool:
    """Check if logged in to WhatsApp Web."""
    return _run_async(_is_logged_in_async())


def find_group(group_name: Optional[str] = None) -> bool:
    """Navigate to a group."""
    return _run_async(_find_group_async(group_name or WHATSAPP_GROUP))


def send_message(text: str) -> bool:
    """Send a message in the current chat."""
    return _run_async(_send_message_async(text))


def send_to_group(text: str, group_name: Optional[str] = None) -> bool:
    """Full pipeline: launch → find group → send."""
    if not launch():
        return False
    if not is_logged_in():
        logger.info("Please scan the QR code in WhatsApp Web.")
        time.sleep(30)  # Give user time to scan
        if not is_logged_in():
            return False
    if not find_group(group_name):
        return False
    return send_message(text)


def close() -> None:
    """Close WhatsApp Web browser."""
    _run_async(_close_async())
