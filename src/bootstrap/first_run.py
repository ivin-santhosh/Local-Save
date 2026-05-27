"""
LinkSync AI — First-Run Bootstrap
====================================
Handles the one-time setup that runs when the user launches
the app for the first time. Orchestrates:

1. Python version check
2. Verify pip dependencies
3. Playwright browser setup
4. Browser discovery
5. WhatsApp discovery
6. Ollama health check
7. Agent context creation
8. Desktop shortcut creation

Each step reports progress to the optional UI callback.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from config import (
    PROJECT_ROOT, CONTEXT_FILE, ICON_PATH,
    BROWSER_REGISTRY,
    WHATSAPP_KNOWN_PATHS, WHATSAPP_STORE_ID, WHATSAPP_DOWNLOAD_URL,
    APP_NAME,
)

logger = logging.getLogger(__name__)


def is_first_run() -> bool:
    """
    Check if this is the first time the app is running.

    Returns:
        True if agent_context.json doesn't exist yet.
    """
    return not CONTEXT_FILE.exists()


def run_bootstrap(
    progress_callback: Optional[Callable[[int, bool, str], None]] = None,
) -> bool:
    """
    Run the full first-time setup.

    Args:
        progress_callback: Optional callback(step_index, success, detail).
            step_index is 0-based matching BOOTSTRAP_STEPS in progress_window.

    Returns:
        True if all critical steps succeeded.
    """
    def _report(step: int, success: bool, detail: str = "") -> None:
        logger.info("Bootstrap step %d: %s — %s", step, "OK" if success else "FAIL", detail)
        if progress_callback:
            progress_callback(step, success, detail)

    all_ok = True

    # ── Step 0: Python version ──
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        _report(0, True, f"Python {py_version}")
    else:
        _report(0, False, f"Python {py_version} — requires 3.10+")
        all_ok = False

    # ── Step 1: Dependencies ──
    try:
        import langchain
        import customtkinter
        import pystray
        _report(1, True, "All packages installed")
    except ImportError as exc:
        _report(1, False, f"Missing: {exc.name}")
        all_ok = False

    # ── Step 2: Playwright ──
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        _report(2, True, "Chromium ready")
    except Exception as exc:
        _report(2, False, f"Run: playwright install chromium")
        # Non-critical — scraping will fail but core app works

    # ── Step 3: Discover browsers ──
    discovered_browsers = []
    for proc_name, info in BROWSER_REGISTRY.items():
        for known_path_template in info.get("known_paths", []):
            path = known_path_template.replace("{user}", os.getlogin())
            if os.path.isfile(path):
                discovered_browsers.append(info["name"])
                break
    _report(3, True, f"Found: {', '.join(discovered_browsers) or 'none (will auto-detect)'}")

    # ── Step 4: Discover WhatsApp ──
    whatsapp_found = False
    whatsapp_path = None
    for path_template in WHATSAPP_KNOWN_PATHS:
        path = path_template.replace("{user}", os.getlogin())
        if os.path.isfile(path):
            whatsapp_found = True
            whatsapp_path = path
            break
        elif os.path.isdir(path):
            # Search inside directory
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.lower() == "whatsapp.exe":
                        whatsapp_path = os.path.join(root, f)
                        whatsapp_found = True
                        break
                if whatsapp_found:
                    break

    if whatsapp_found:
        _report(4, True, f"Found: {whatsapp_path}")
    else:
        _report(4, False, "Not found — will search on first sync")

    # ── Step 5: Ollama ──
    try:
        from src.brain.llm_provider import check_ollama_health
        if check_ollama_health():
            _report(5, True, "Ollama running")
        else:
            _report(5, False, "Not running — start Ollama or configure API key")
    except Exception:
        _report(5, False, "Cannot check Ollama")

    # ── Step 6: Create agent context ──
    try:
        from src.storage.context_manager import load_context, set_value

        # Load creates default context if missing
        ctx = load_context()

        # Store discovered data
        if whatsapp_path:
            set_value("discovered_apps.whatsapp", {
                "path": whatsapp_path,
                "method": "bootstrap_discovery",
            })

        for browser_name in discovered_browsers:
            key = browser_name.lower().replace(" ", "_")
            set_value(f"discovered_apps.browsers.{key}", True)

        _report(6, True, "Context initialized")
    except Exception as exc:
        _report(6, False, str(exc))
        all_ok = False

    # ── Step 7: Desktop shortcut ──
    try:
        created = create_desktop_shortcut()
        _report(7, created, "Shortcut created" if created else "Skipped")
    except Exception as exc:
        _report(7, False, str(exc))

    return all_ok


def create_desktop_shortcut() -> bool:
    """
    Create a desktop shortcut (.lnk) to LinkSync_AI.bat.

    Uses the Windows Script Host COM object to create a proper
    shortcut with the correct icon.

    Returns:
        True if the shortcut was created.
    """
    try:
        import winshell
        desktop = winshell.desktop()
    except ImportError:
        # Fallback: find desktop manually
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

    shortcut_path = os.path.join(desktop, f"{APP_NAME}.lnk")

    if os.path.exists(shortcut_path):
        logger.info("Desktop shortcut already exists.")
        return True

    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = str(PROJECT_ROOT / "LinkSync_AI.bat")
        shortcut.WorkingDirectory = str(PROJECT_ROOT)
        shortcut.Description = "LinkSync AI — Browser-to-WhatsApp sync agent"

        if ICON_PATH.exists():
            shortcut.IconLocation = str(ICON_PATH)

        shortcut.save()
        logger.info("Desktop shortcut created: %s", shortcut_path)
        return True

    except ImportError:
        logger.warning(
            "win32com not available. Creating a simple .bat shortcut instead."
        )
        # Fallback: create a simple .bat file
        bat_shortcut = os.path.join(desktop, f"{APP_NAME}.bat")
        with open(bat_shortcut, "w") as f:
            f.write(f'@echo off\ncd /d "{PROJECT_ROOT}"\ncall LinkSync_AI.bat\n')
        return True

    except Exception as exc:
        logger.error("Failed to create shortcut: %s", exc)
        return False
