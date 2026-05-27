"""
LinkSync AI — Multi-Browser Tab Capture
=========================================
Auto-detects the foreground browser (Chrome, Edge, Brave, Opera,
DuckDuckGo, Vivaldi, Firefox, or any Chromium-based browser) and
captures all open tab titles and URLs.

Primary method: Chrome DevTools Protocol (CDP) — gets ALL tabs.
Fallback method: pywinauto UIA — gets active tab only.

The BROWSER_REGISTRY in config.py makes this fully extensible:
add a new browser by adding one dict entry, zero code changes.

Usage:
    from src.capture.tab_capture import capture_tabs
    browser_name, tabs = capture_tabs()
"""

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import requests
import win32gui
import win32process

from config import BROWSER_REGISTRY, CDP_PORT, CDP_URL

logger = logging.getLogger(__name__)


def _get_process_name(pid: int) -> Optional[str]:
    """
    Get the executable name for a given process ID.

    Uses psutil if available, falls back to win32 API.

    Args:
        pid: Windows process ID.

    Returns:
        Lowercase process name (e.g., 'chrome.exe') or None.
    """
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.name().lower()
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: use win32 API
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)
                ):
                    return os.path.basename(buf.value).lower()
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
    except Exception as exc:
        logger.debug("Failed to get process name for PID %d: %s", pid, exc)

    return None


def detect_active_browser() -> Optional[dict]:
    """
    Detect the foreground browser window.

    Uses win32gui to get the foreground window, then resolves
    its process name and matches against BROWSER_REGISTRY.

    Returns:
        Browser info dict from BROWSER_REGISTRY with added 'process' key,
        or None if the foreground window is not a known browser.
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return None

        process_name = _get_process_name(pid)
        if not process_name:
            return None

        # Match against registry
        if process_name in BROWSER_REGISTRY:
            info = BROWSER_REGISTRY[process_name].copy()
            info["process"] = process_name
            info["hwnd"] = hwnd
            info["window_title"] = win32gui.GetWindowText(hwnd)
            logger.info("Detected browser: %s (pid=%d)", info["name"], pid)
            return info

        # Check if window title suggests a browser
        title = win32gui.GetWindowText(hwnd).lower()
        for proc_name, info in BROWSER_REGISTRY.items():
            if info["name"].lower() in title:
                result = info.copy()
                result["process"] = proc_name
                result["hwnd"] = hwnd
                result["window_title"] = win32gui.GetWindowText(hwnd)
                logger.info(
                    "Detected browser by title match: %s", info["name"]
                )
                return result

        logger.info(
            "Foreground window '%s' (%s) is not a known browser.",
            win32gui.GetWindowText(hwnd),
            process_name,
        )
        return None

    except Exception as exc:
        logger.error("Error detecting browser: %s", exc)
        return None


def get_all_tabs_cdp() -> list[dict]:
    """
    Get all open tabs via Chrome DevTools Protocol.

    Connects to the CDP endpoint (localhost:{CDP_PORT}/json) and
    retrieves all page targets. Works for ANY Chromium-based browser
    (Chrome, Edge, Brave, Opera, DuckDuckGo, Vivaldi).

    Returns:
        List of dicts with 'title' and 'url' keys.
        Empty list if CDP is not available.
    """
    try:
        response = requests.get(CDP_URL, timeout=3)
        response.raise_for_status()
        targets = response.json()

        tabs = []
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                title = target.get("title", "Untitled")

                # Skip internal browser pages
                if url.startswith(("chrome://", "edge://", "brave://",
                                   "opera://", "vivaldi://", "about:")):
                    continue

                tabs.append({
                    "title": title,
                    "url": url,
                    "domain": urlparse(url).netloc if url else "",
                })

        logger.info("CDP captured %d tabs.", len(tabs))
        return tabs

    except requests.ConnectionError:
        logger.debug("CDP not available (port %d not listening).", CDP_PORT)
        return []
    except Exception as exc:
        logger.warning("CDP tab capture failed: %s", exc)
        return []


def get_tabs_uia(browser_info: Optional[dict] = None) -> list[dict]:
    """
    Get tab information using pywinauto UI Automation (fallback).

    This method reads the address bar for the active tab URL and
    attempts to enumerate TabItem controls for all tab titles.
    Works for all browsers including Firefox.

    Args:
        browser_info: Optional browser info dict with 'title_pattern'.

    Returns:
        List of dicts with 'title' and 'url' keys.
        May return only the active tab if full enumeration fails.
    """
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")

        # Find the browser window
        if browser_info and "title_pattern" in browser_info:
            import re
            pattern = browser_info["title_pattern"]
            windows = desktop.windows(title_re=pattern)
        else:
            # Try the foreground window directly
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            windows = desktop.windows(title=title)

        if not windows:
            logger.warning("No browser window found via UIA.")
            return []

        browser_window = windows[0]
        tabs = []

        # Try to enumerate all tab items
        try:
            tab_items = browser_window.descendants(control_type="TabItem")
            for tab_item in tab_items:
                tab_title = tab_item.window_text()
                if tab_title and tab_title not in ("New Tab", ""):
                    tabs.append({
                        "title": tab_title,
                        "url": "",  # UIA can't get URL for inactive tabs
                        "domain": "",
                    })
        except Exception as exc:
            logger.debug("Could not enumerate tab items: %s", exc)

        # Get the active tab's URL from the address bar
        try:
            address_bar = browser_window.child_window(
                title="Address and search bar", control_type="Edit"
            )
            active_url = address_bar.get_value()
            if active_url:
                # If we didn't get tabs, at least return the active one
                if not tabs:
                    active_title = browser_window.window_text()
                    # Browser titles usually end with " - Browser Name"
                    page_title = active_title.rsplit(" - ", 1)[0] if " - " in active_title else active_title
                    tabs.append({
                        "title": page_title,
                        "url": active_url,
                        "domain": urlparse(active_url).netloc,
                    })
                else:
                    # Attach URL to the last tab (usually the active one)
                    tabs[-1]["url"] = active_url
                    tabs[-1]["domain"] = urlparse(active_url).netloc
        except Exception as exc:
            logger.debug("Could not read address bar: %s", exc)

        logger.info("UIA captured %d tabs.", len(tabs))
        return tabs

    except ImportError:
        logger.error("pywinauto not installed. Cannot use UIA fallback.")
        return []
    except Exception as exc:
        logger.error("UIA tab capture failed: %s", exc)
        return []


def capture_tabs() -> tuple[str, list[dict]]:
    """
    Main entry point: auto-detect the browser and capture all tabs.

    Strategy:
    1. Detect the foreground browser
    2. If Chromium-based → try CDP first → fall back to UIA
    3. If non-Chromium (Firefox) → use UIA directly
    4. If no browser detected → return empty

    Returns:
        Tuple of (browser_name, list_of_tab_dicts).
        Each tab dict has: title, url, domain.
    """
    browser = detect_active_browser()

    if browser is None:
        logger.info("No browser detected in foreground.")
        return ("Unknown", [])

    browser_name = browser.get("name", "Unknown Browser")
    is_chromium = browser.get("chromium", False)

    # Strategy 1: CDP for Chromium browsers
    if is_chromium:
        tabs = get_all_tabs_cdp()
        if tabs:
            return (browser_name, tabs)
        logger.info(
            "CDP unavailable for %s. Falling back to UIA.", browser_name
        )

    # Strategy 2: UIA fallback (works for all browsers)
    tabs = get_tabs_uia(browser)
    return (browser_name, tabs)
