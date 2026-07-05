"""
LinkSync AI — Multi-Browser Tab Capture
=========================================
Auto-detects browsers and captures all open tab titles and URLs.

Two modes:
  • capture_all_browsers() — scans ALL running browser processes
    via psutil and collects tabs from every one of them.
  • capture_tabs() — tries capture_all_browsers() first; falls
    back to foreground-only detection if nothing is found.

Primary method: Chrome DevTools Protocol (CDP) — gets ALL tabs.
Fallback method: pywinauto UIA — gets active tab only.

The BROWSER_REGISTRY in config.py makes this fully extensible:
add a new browser by adding one dict entry, zero code changes.

Usage:
    from src.capture.tab_capture import capture_tabs, capture_all_browsers
    browser_name, tabs = capture_tabs()
    all_tabs = capture_all_browsers()   # list[dict] with 'browser' key
"""

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import psutil

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
    Enumerates all windows for the browser.

    Args:
        browser_info: Optional browser info dict with 'title_pattern'.

    Returns:
        List of dicts with 'title', 'url', 'window_index', 'window_title' keys.
    """
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")

        # Find the browser window
        if browser_info and "title_pattern" in browser_info:
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

        all_tabs = []
        for win_idx, browser_window in enumerate(windows, start=1):
            try:
                window_title = browser_window.window_text()
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
                                "window_index": win_idx,
                                "window_title": window_title,
                            })
                except Exception as exc:
                    logger.debug("Could not enumerate tab items for window %d: %s", win_idx, exc)

                # Get the active tab's URL from the address bar
                try:
                    address_bar = browser_window.child_window(
                        title="Address and search bar", control_type="Edit"
                    )
                    active_url = address_bar.get_value()
                    if active_url:
                        # If we didn't get tabs, at least return the active one
                        if not tabs:
                            # Browser titles usually end with " - Browser Name"
                            page_title = window_title.rsplit(" - ", 1)[0] if " - " in window_title else window_title
                            tabs.append({
                                "title": page_title,
                                "url": active_url,
                                "domain": urlparse(active_url).netloc,
                                "window_index": win_idx,
                                "window_title": window_title,
                            })
                        else:
                            # Attach URL to the last tab (usually the active one)
                            tabs[-1]["url"] = active_url
                            tabs[-1]["domain"] = urlparse(active_url).netloc
                except Exception as exc:
                    logger.debug("Could not read address bar for window %d: %s", win_idx, exc)

                all_tabs.extend(tabs)
            except Exception as exc:
                logger.error("Error processing window %d: %s", win_idx, exc)

        logger.info("UIA captured %d tabs from %d windows.", len(all_tabs), len(windows))
        return all_tabs

    except ImportError:
        logger.error("pywinauto not installed. Cannot use UIA fallback.")
        return []
    except Exception as exc:
        logger.error("UIA tab capture failed: %s", exc)
        return []


def capture_all_browsers() -> list[dict]:
    """
    Scan ALL running browser processes and collect tabs from each.

    Strategy:
      1. Use psutil.process_iter() to find every running process whose
         name matches a BROWSER_REGISTRY key.
      2. For each *Chromium* browser found → try CDP.
      3. For each *non-Chromium* browser found (Firefox) → try UIA.
      4. Deduplicate tabs by URL (first occurrence wins).
      5. Each returned tab dict includes a 'browser' key.

    Returns:
        List of tab dicts.  Each dict has keys:
        title, url, domain, browser.
    """
    found_browsers: dict[str, dict] = {}  # proc_name → registry entry

    # --- Step 1: discover running browsers -----------------------
    try:
        for proc in psutil.process_iter(["name"]):
            try:
                pname = (proc.info["name"] or "").lower()
                if pname in BROWSER_REGISTRY and pname not in found_browsers:
                    found_browsers[pname] = BROWSER_REGISTRY[pname]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        logger.warning("psutil process scan failed: %s", exc)
        return []

    if not found_browsers:
        logger.info("capture_all_browsers: no known browser processes running.")
        return []

    logger.info(
        "capture_all_browsers: found %d browser(s): %s",
        len(found_browsers),
        ", ".join(info["name"] for info in found_browsers.values()),
    )

    all_tabs: list[dict] = []

    # --- Step 2 & 3: collect tabs from each browser --------------
    for proc_name, info in found_browsers.items():
        browser_name = info["name"]
        is_chromium = info.get("chromium", False)
        tabs: list[dict] = []

        if is_chromium:
            tabs = get_all_tabs_cdp()
            if not tabs:
                logger.debug(
                    "CDP returned no tabs for %s; trying UIA.", browser_name
                )
                tabs = get_tabs_uia(info)
        else:
            # Non-Chromium (e.g. Firefox) — UIA only
            tabs = get_tabs_uia(info)

        # Tag every tab with its source browser
        for tab in tabs:
            tab["browser"] = browser_name

        all_tabs.extend(tabs)

    # --- Step 4: deduplicate by URL (first occurrence wins) ------
    seen_urls: set[str] = set()
    unique_tabs: list[dict] = []
    for tab in all_tabs:
        url = tab.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        unique_tabs.append(tab)

    logger.info(
        "capture_all_browsers: %d unique tabs across %d browser(s).",
        len(unique_tabs),
        len(found_browsers),
    )
    return unique_tabs


def capture_tabs() -> tuple[str, list[dict]]:
    """
    Main entry point: capture tabs from ALL running browsers.

    Strategy:
    1. Scan ALL running browsers (multi-browser mode)
    2. If that fails, fall back to foreground-only detection
    3. If no browser detected → return empty

    Returns:
        Tuple of (browser_name, list_of_tab_dicts).
        Each tab dict has: title, url, domain, browser.
    """
    # Strategy 1: Scan all running browsers
    all_tabs = capture_all_browsers()
    if all_tabs:
        browsers_found = {t["browser"] for t in all_tabs if "browser" in t}
        if len(browsers_found) == 1:
            return (browsers_found.pop(), all_tabs)
        return (" + ".join(sorted(browsers_found)), all_tabs)

    # Strategy 2: Foreground-only fallback
    logger.info("Multi-browser scan found nothing. Trying foreground detection...")
    browser = detect_active_browser()

    if browser is None:
        logger.info("No browser detected in foreground.")
        return ("Unknown", [])

    browser_name = browser.get("name", "Unknown Browser")
    is_chromium = browser.get("chromium", False)

    if is_chromium:
        tabs = get_all_tabs_cdp()
        if tabs:
            for tab in tabs:
                tab["browser"] = browser_name
            return (browser_name, tabs)
        logger.info(
            "CDP unavailable for %s. Falling back to UIA.", browser_name
        )

    tabs = get_tabs_uia(browser)
    for tab in tabs:
        tab["browser"] = browser_name
    return (browser_name, tabs)
