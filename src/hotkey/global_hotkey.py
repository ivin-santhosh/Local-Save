"""
LinkSync AI — Global Hotkey Handler
====================================
Registers a system-wide hotkey (Ctrl+Shift+L) using the native
Windows RegisterHotKey API via ctypes. This does NOT require
administrator privileges — it uses the standard Windows message
loop mechanism that all desktop apps use.

If the primary hotkey is already taken by another application,
it automatically falls back to Ctrl+Shift+K and notifies the user.

Usage:
    from src.hotkey.global_hotkey import start_listener, stop_listener
    start_listener(callback=my_function)
"""

import ctypes
import ctypes.wintypes
import threading
import logging
from typing import Callable, Optional

import win32con

from config import (
    HOTKEY_ID,
    HOTKEY_MODIFIERS,
    HOTKEY_VK,
    HOTKEY_FALLBACK_VK,
    HOTKEY_DISPLAY,
)

logger = logging.getLogger(__name__)

# Module-level state
_listener_thread: Optional[threading.Thread] = None
_running = False
_registered_vk: Optional[int] = None


def register_hotkey() -> bool:
    """
    Register the global hotkey with the Windows OS.

    Tries the primary hotkey (Ctrl+Shift+L) first. If that fails
    (e.g., another app already uses it), falls back to Ctrl+Shift+K.

    Returns:
        True if registration succeeded, False if both attempts failed.
    """
    global _registered_vk

    # Try primary hotkey
    if ctypes.windll.user32.RegisterHotKey(
        None, HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_VK
    ):
        _registered_vk = HOTKEY_VK
        logger.info("Global hotkey registered: %s", HOTKEY_DISPLAY)
        return True

    logger.warning(
        "Primary hotkey %s already in use. Trying fallback...",
        HOTKEY_DISPLAY,
    )

    # Try fallback hotkey
    if ctypes.windll.user32.RegisterHotKey(
        None, HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_FALLBACK_VK
    ):
        _registered_vk = HOTKEY_FALLBACK_VK
        fallback_display = f"Ctrl+Shift+{chr(HOTKEY_FALLBACK_VK)}"
        logger.info("Fallback hotkey registered: %s", fallback_display)

        # Notify user about the change
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                "LinkSync AI — Hotkey Changed",
                f"{HOTKEY_DISPLAY} was taken. Using {fallback_display} instead.",
                duration=5,
                threaded=True,
            )
        except Exception:
            logger.debug("Toast notification unavailable for hotkey change")

        return True

    logger.error("Failed to register any global hotkey.")
    return False


def unregister_hotkey() -> None:
    """Unregister the global hotkey and release the OS binding."""
    global _registered_vk

    if _registered_vk is not None:
        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        logger.info("Global hotkey unregistered.")
        _registered_vk = None


def _hotkey_listener(callback: Callable[[], None]) -> None:
    """
    Internal: Run the Win32 message loop that listens for hotkey events.

    This function blocks and should be run in a daemon thread.
    When WM_HOTKEY is received, it calls the provided callback.

    Args:
        callback: Function to call when the hotkey is pressed.
    """
    global _running

    if not register_hotkey():
        logger.error("Cannot start hotkey listener — registration failed.")
        return

    _running = True
    logger.info("Hotkey listener started.")

    msg = ctypes.wintypes.MSG()
    try:
        while _running:
            # GetMessageW blocks until a message arrives
            # Returns 0 for WM_QUIT, -1 for error
            result = ctypes.windll.user32.GetMessageW(
                ctypes.byref(msg), None, 0, 0
            )

            if result == 0 or result == -1:
                break

            if msg.message == win32con.WM_HOTKEY and msg.wParam == HOTKEY_ID:
                logger.info("Hotkey pressed! Triggering sync cycle.")
                try:
                    callback()
                except Exception as exc:
                    logger.error("Error in hotkey callback: %s", exc)

            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        unregister_hotkey()
        _running = False
        logger.info("Hotkey listener stopped.")


def start_listener(callback: Callable[[], None]) -> threading.Thread:
    """
    Start the global hotkey listener in a background daemon thread.

    Args:
        callback: Function to call when the user presses the hotkey.

    Returns:
        The listener thread (for reference; it's a daemon so it
        won't prevent app shutdown).
    """
    global _listener_thread

    if _listener_thread is not None and _listener_thread.is_alive():
        logger.warning("Hotkey listener already running.")
        return _listener_thread

    _listener_thread = threading.Thread(
        target=_hotkey_listener,
        args=(callback,),
        daemon=True,
        name="HotkeyListener",
    )
    _listener_thread.start()
    return _listener_thread


def stop_listener() -> None:
    """
    Stop the hotkey listener by posting a WM_QUIT message
    to its message loop, causing it to exit cleanly.
    """
    global _running
    _running = False

    # Post WM_QUIT to break the GetMessage loop
    if _listener_thread is not None and _listener_thread.is_alive():
        ctypes.windll.user32.PostThreadMessageW(
            _listener_thread.ident, win32con.WM_QUIT, 0, 0
        )
        _listener_thread.join(timeout=3)
        logger.info("Hotkey listener thread joined.")


def get_active_hotkey_display() -> str:
    """Return a human-readable string of the currently active hotkey."""
    if _registered_vk is None:
        return "(not registered)"
    return f"Ctrl+Shift+{chr(_registered_vk)}"
