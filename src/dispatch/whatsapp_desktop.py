"""
LinkSync AI — WhatsApp Desktop Automation
===========================================
Automates the WhatsApp Desktop app (Windows) using pywinauto
UIA backend. Handles:

- Launching/focusing the app
- Finding a group by name
- Sending formatted messages
- Self-healing element discovery (no hardcoded AutomationIds)

Element paths are cached in the database for faster future lookups.
"""

import logging
import subprocess
import time
from typing import Optional

from config import WHATSAPP_GROUP

logger = logging.getLogger(__name__)


def is_whatsapp_running() -> bool:
    """
    Check if WhatsApp Desktop is currently running.

    Returns:
        True if WhatsApp.exe is found in running processes.
    """
    try:
        import psutil
        for proc in psutil.process_iter(attrs=["name"]):
            if proc.info["name"] and "whatsapp" in proc.info["name"].lower():
                return True
    except ImportError:
        # Fallback: use tasklist command
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq WhatsApp.exe"],
                capture_output=True, text=True, timeout=5,
            )
            return "WhatsApp.exe" in result.stdout
        except Exception:
            pass
    except Exception as exc:
        logger.debug("Process check error: %s", exc)
    return False


def launch_whatsapp(path: str, timeout: int = 15) -> bool:
    """
    Launch or focus the WhatsApp Desktop app.

    Args:
        path: Full path to WhatsApp.exe.
        timeout: Seconds to wait for the window to appear.

    Returns:
        True if WhatsApp window is detected.
    """
    try:
        if not is_whatsapp_running():
            logger.info("Launching WhatsApp from: %s", path)
            subprocess.Popen([path], shell=False)
        else:
            logger.info("WhatsApp already running. Focusing...")

        # Wait for the window
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")

        for _ in range(timeout * 2):  # Check every 0.5s
            windows = desktop.windows(title_re=".*WhatsApp.*")
            if windows:
                windows[0].set_focus()
                time.sleep(1)  # Let the UI settle
                logger.info("WhatsApp window focused.")
                return True
            time.sleep(0.5)

        logger.warning("WhatsApp window not found after %ds.", timeout)
        return False

    except Exception as exc:
        logger.error("Failed to launch WhatsApp: %s", exc)
        return False


def _get_whatsapp_window():
    """
    Get the WhatsApp main window via pywinauto.

    Returns:
        pywinauto window wrapper, or None.
    """
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        windows = desktop.windows(title_re=".*WhatsApp.*")
        if windows:
            return windows[0]
    except Exception as exc:
        logger.error("Cannot find WhatsApp window: %s", exc)
    return None


def _discover_element(window, control_type: str, title_patterns: list[str]):
    """
    Self-healing element discovery.

    Tries multiple title patterns to find a UI element. This makes
    the automation resilient to WhatsApp UI updates that change
    element labels.

    Args:
        window: pywinauto window to search in.
        control_type: UIA control type (e.g., "Edit", "Button").
        title_patterns: List of possible title strings to try.

    Returns:
        The found element, or None.
    """
    for pattern in title_patterns:
        try:
            element = window.child_window(
                title_re=f".*{pattern}.*",
                control_type=control_type,
            )
            if element.exists(timeout=2):
                return element
        except Exception:
            continue

    # Last resort: find any element of that control type
    try:
        elements = window.descendants(control_type=control_type)
        if elements:
            logger.debug(
                "Found %d %s elements via fallback scan.",
                len(elements), control_type,
            )
            return elements[0]
    except Exception:
        pass

    return None


def find_group(group_name: Optional[str] = None) -> bool:
    """
    Navigate to a WhatsApp group by searching for its name.

    Args:
        group_name: Group name to search for (default: from config).

    Returns:
        True if the group was found and opened.
    """
    group_name = group_name or WHATSAPP_GROUP
    window = _get_whatsapp_window()
    if not window:
        return False

    try:
        # Find and click the search bar
        search_bar = _discover_element(window, "Edit", [
            "Search", "Search or start", "Type to search",
            "Search input", "search",
        ])
        if not search_bar:
            logger.error("Cannot find WhatsApp search bar.")
            return False

        search_bar.click_input()
        time.sleep(0.5)

        # Clear existing text and type group name
        search_bar.type_keys("^a{BACKSPACE}", with_spaces=True)  # Select all and delete
        time.sleep(0.2)
        search_bar.type_keys(group_name, with_spaces=True)
        time.sleep(2)  # Wait for search results

        # Click the first matching result
        try:
            result = window.child_window(
                title_re=f".*{group_name}.*",
                control_type="ListItem",
            )
            if result.exists(timeout=3):
                result.click_input()
                time.sleep(1)
                logger.info("Opened WhatsApp group: %s", group_name)
                return True
        except Exception:
            pass

        # Fallback: press Enter to select first result
        search_bar.type_keys("{ENTER}")
        time.sleep(1)
        logger.info("Selected first search result for: %s", group_name)
        return True

    except Exception as exc:
        logger.error("Failed to find group '%s': %s", group_name, exc)
        return False


def send_message(text: str) -> bool:
    """
    Send a message in the currently open WhatsApp chat.

    Uses clipboard copy-paste to send messages quickly and reliably
    without typing issues or focus losses. Backups and restores the clipboard.

    Args:
        text: The message text to send.

    Returns:
        True if the message was sent successfully.
    """
    window = _get_whatsapp_window()
    if not window:
        return False

    try:
        # Locate search bar first to exclude it
        search_bar = _discover_element(window, "Edit", [
            "Search", "Search or start", "Type to search",
            "Search input", "search",
        ])

        # Find the message input field (excluding search bar)
        msg_input = None
        msg_title_patterns = [
            "Type a message", "Message", "message input",
            "Type a message…", "Write a message",
        ]
        for pattern in msg_title_patterns:
            try:
                el = window.child_window(
                    title_re=f".*{pattern}.*",
                    control_type="Edit",
                )
                if el.exists(timeout=2):
                    if search_bar and el == search_bar:
                        continue
                    msg_input = el
                    break
            except Exception:
                continue

        # Descendant fallback if title matches fail
        if not msg_input:
            try:
                edits = window.descendants(control_type="Edit")
                for edit in edits:
                    if search_bar and edit == search_bar:
                        continue
                    msg_input = edit
                    break
            except Exception as exc:
                logger.debug("Failed to find message input via descendants: %s", exc)

        if not msg_input:
            logger.error("Cannot find WhatsApp message input.")
            return False

        # Backup clipboard content
        import win32clipboard
        import win32con
        old_text = ""
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                old_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        # Copy message to clipboard
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception as exc:
            logger.error("Failed to copy message to clipboard: %s", exc)
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return False

        # Focus and paste
        msg_input.set_focus()
        time.sleep(0.3)
        msg_input.click_input()
        time.sleep(0.2)
        msg_input.type_keys("^v", with_spaces=True)
        time.sleep(0.3)

        # Restore clipboard
        if old_text:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(old_text, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

        # Click send or press Enter
        send_btn = _discover_element(window, "Button", [
            "Send", "send", "Send message",
        ])
        if send_btn:
            send_btn.click_input()
        else:
            msg_input.type_keys("{ENTER}")

        time.sleep(1.0)
        logger.info("Message sent via WhatsApp Desktop UWP (Clipboard Paste).")
        return True

    except Exception as exc:
        logger.error("Failed to send message: %s", exc)
        return False


def send_to_group(
    text: str,
    group_name: Optional[str] = None,
    whatsapp_path: Optional[str] = None,
) -> bool:
    """
    Full pipeline: launch WhatsApp → find group → send message.

    Args:
        text: Message to send.
        group_name: Target group (default: from config).
        whatsapp_path: Path to WhatsApp.exe (skips launch if None and already running).

    Returns:
        True if message was sent successfully.
    """
    # Ensure WhatsApp is running
    if whatsapp_path and not is_whatsapp_running():
        if not launch_whatsapp(whatsapp_path):
            return False

    if not is_whatsapp_running():
        logger.error("WhatsApp is not running and no path provided.")
        return False

    # Navigate to group
    if not find_group(group_name):
        return False

    # Send the message
    return send_message(text)


def send_to_group_uia(text: str, group_name: str) -> bool:
    """
    Send a message to a group via UIA (UI Automation) fallback.
    Specifically useful for UWP apps already launched.
    """
    return send_to_group(text, group_name)
