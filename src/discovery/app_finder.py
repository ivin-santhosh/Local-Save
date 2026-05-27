"""
LinkSync AI — Intelligent App Discovery
=========================================
Finds any application on the user's system using a 6-step
intelligence hierarchy:

1. REMEMBER — Check agent_context.json for cached path
2. DISCOVER — Search known installation directories
3. REGISTRY — Check Windows Registry for installed apps
4. SCAN C: — Recursive drive search (threaded, with progress)
5. SCAN D: — Fallback to secondary drive
6. INSTALL — Offer to install from official source

Every discovered path is cached in agent_context.json so the
next lookup is instant.

Usage:
    from src.discovery.app_finder import find_app
    path = find_app("WhatsApp", "WhatsApp.exe", known_paths, "whatsapp")
"""

import logging
import os
import subprocess
import threading
import winreg
from pathlib import Path
from typing import Callable, Optional

from src.storage.context_manager import get_value, set_value

logger = logging.getLogger(__name__)

# Directories to skip during recursive search (performance + safety)
_SKIP_DIRS = {
    "$recycle.bin", "system volume information", "windows",
    "windows.old", "programdata", "recovery", ".git",
    "node_modules", "__pycache__", ".venv", "venv",
}


def find_app(
    app_name: str,
    exe_name: str,
    known_paths: list[str],
    context_key: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Find an application on the system using the 6-step hierarchy.

    Args:
        app_name: Human-readable name (e.g., "WhatsApp").
        exe_name: Executable filename (e.g., "WhatsApp.exe").
        known_paths: List of common install paths to check first.
        context_key: Key in agent_context.json under 'discovered_apps'.
        progress_callback: Optional callback for UI progress updates.

    Returns:
        Absolute path to the executable, or None if not found.
    """
    def _report(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # ── Step 1: Check cached context ──
    _report(f"Checking cached path for {app_name}...")
    cached_path = get_value(f"discovered_apps.{context_key}.path")
    if cached_path and os.path.isfile(cached_path):
        _report(f"Found {app_name} in cache: {cached_path}")
        return cached_path
    elif cached_path:
        _report(f"Cached path stale (file missing): {cached_path}")

    # ── Step 2: Search known paths ──
    _report(f"Searching known locations for {app_name}...")
    username = os.getlogin()
    for path_template in known_paths:
        path = path_template.replace("{user}", username)
        if os.path.isfile(path):
            _report(f"Found {app_name}: {path}")
            cache_discovery(context_key, path)
            return path
        # Also check if it's a directory — search inside it
        if os.path.isdir(path):
            found = _search_directory(path, exe_name)
            if found:
                _report(f"Found {app_name}: {found}")
                cache_discovery(context_key, found)
                return found

    # ── Step 3: Check Windows Registry ──
    _report(f"Searching Windows Registry for {app_name}...")
    reg_path = _search_registry(app_name, exe_name)
    if reg_path:
        _report(f"Found {app_name} in registry: {reg_path}")
        cache_discovery(context_key, reg_path)
        return reg_path

    # ── Step 4: Scan C: drive ──
    _report(f"Scanning C: drive for {exe_name}... (this may take a moment)")
    c_result = search_drive("C:\\", exe_name, progress_callback)
    if c_result:
        _report(f"Found {app_name} on C: drive: {c_result}")
        cache_discovery(context_key, c_result)
        return c_result

    # ── Step 5: Scan D: drive ──
    if os.path.isdir("D:\\"):
        _report(f"Scanning D: drive for {exe_name}...")
        d_result = search_drive("D:\\", exe_name, progress_callback)
        if d_result:
            _report(f"Found {app_name} on D: drive: {d_result}")
            cache_discovery(context_key, d_result)
            return d_result

    # ── Step 6: Not found ──
    _report(f"{app_name} not found on this system.")
    return None


def _search_directory(directory: str, exe_name: str) -> Optional[str]:
    """
    Search a specific directory (non-recursive) for an executable.

    Args:
        directory: Path to search.
        exe_name: Executable filename to find.

    Returns:
        Full path if found, None otherwise.
    """
    try:
        for item in os.listdir(directory):
            if item.lower() == exe_name.lower():
                full_path = os.path.join(directory, item)
                if os.path.isfile(full_path):
                    return full_path
    except PermissionError:
        pass
    except Exception as exc:
        logger.debug("Error searching %s: %s", directory, exc)
    return None


def _search_registry(app_name: str, exe_name: str) -> Optional[str]:
    """
    Search Windows Registry for installed applications.

    Checks both HKLM and HKCU Uninstall keys for matching entries.

    Args:
        app_name: Application name to search for.
        exe_name: Executable name to verify path.

    Returns:
        Full path to executable if found, None otherwise.
    """
    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, key_path in registry_paths:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                display_name = winreg.QueryValueEx(
                                    subkey, "DisplayName"
                                )[0]
                            except FileNotFoundError:
                                continue

                            if app_name.lower() in display_name.lower():
                                # Try InstallLocation
                                try:
                                    install_loc = winreg.QueryValueEx(
                                        subkey, "InstallLocation"
                                    )[0]
                                    if install_loc:
                                        exe_path = os.path.join(
                                            install_loc, exe_name
                                        )
                                        if os.path.isfile(exe_path):
                                            return exe_path
                                except FileNotFoundError:
                                    pass

                                # Try DisplayIcon (often points to exe)
                                try:
                                    icon_path = winreg.QueryValueEx(
                                        subkey, "DisplayIcon"
                                    )[0]
                                    # Remove icon index if present
                                    icon_path = icon_path.split(",")[0].strip('"')
                                    if os.path.isfile(icon_path):
                                        return icon_path
                                except FileNotFoundError:
                                    pass

                    except OSError:
                        continue
        except OSError:
            continue

    return None


def search_drive(
    drive: str,
    exe_name: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    timeout: int = 60,
) -> Optional[str]:
    """
    Recursively search a drive for an executable.

    Uses a threaded approach with a timeout to prevent hanging
    on large drives.

    Args:
        drive: Drive root (e.g., "C:\\").
        exe_name: Filename to search for.
        progress_callback: Optional progress reporter.
        timeout: Maximum seconds to search.

    Returns:
        Full path if found, None if not found within timeout.
    """
    result: list[str] = []
    stop_event = threading.Event()

    def _search() -> None:
        try:
            for dirpath, dirnames, filenames in os.walk(drive):
                if stop_event.is_set():
                    return

                # Skip system and irrelevant directories
                dirnames[:] = [
                    d for d in dirnames
                    if d.lower() not in _SKIP_DIRS
                ]

                for filename in filenames:
                    if filename.lower() == exe_name.lower():
                        full_path = os.path.join(dirpath, filename)
                        result.append(full_path)
                        stop_event.set()
                        return
        except PermissionError:
            pass
        except Exception as exc:
            logger.debug("Drive search error: %s", exc)

    thread = threading.Thread(target=_search, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        stop_event.set()
        logger.warning("Drive search timed out after %ds.", timeout)

    return result[0] if result else None


def cache_discovery(context_key: str, path: str) -> None:
    """
    Cache a discovered app path in agent_context.json.

    Args:
        context_key: Key under 'discovered_apps' (e.g., 'whatsapp').
        path: Full path to the discovered executable.
    """
    from datetime import datetime
    set_value(f"discovered_apps.{context_key}", {
        "path": path,
        "method": "auto_discovered",
        "last_verified": datetime.now().isoformat(),
    })
    logger.info("Cached discovery: %s → %s", context_key, path)


def install_from_store(store_id: str) -> bool:
    """
    Open the Microsoft Store page for an app.

    Args:
        store_id: Microsoft Store Product ID.

    Returns:
        True if the store was opened successfully.
    """
    try:
        url = f"ms-windows-store://pdp/?productid={store_id}"
        os.startfile(url)
        logger.info("Opened Microsoft Store for product: %s", store_id)
        return True
    except Exception as exc:
        logger.error("Failed to open Microsoft Store: %s", exc)
        return False


def install_from_url(download_url: str) -> bool:
    """
    Open the default browser to an app's official download page.

    Args:
        download_url: URL to the download page.

    Returns:
        True if the browser was opened successfully.
    """
    try:
        import webbrowser
        webbrowser.open(download_url)
        logger.info("Opened download page: %s", download_url)
        return True
    except Exception as exc:
        logger.error("Failed to open download URL: %s", exc)
        return False
