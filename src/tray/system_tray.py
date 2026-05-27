"""
LinkSync AI — System Tray Icon
================================
Creates a persistent Windows system tray icon using pystray.
This is the user's primary interface to the app:

  Left click  → Open Recent Logs
  Right click → Menu: Sync Now, Logs, Settings, Exit

The tray icon runs on the main thread (blocking), while
the hotkey listener and processing run on background threads.
"""

import logging
from typing import Callable, Optional

from PIL import Image
from pystray import Icon, MenuItem, Menu

from config import ICON_PATH, APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


def create_tray(
    on_sync: Callable[[], None],
    on_logs: Callable[[], None],
    on_settings: Callable[[], None],
    on_exit: Callable[[], None],
) -> Icon:
    """
    Create the system tray icon with menu.

    Args:
        on_sync: Callback for "Sync Now" menu item.
        on_logs: Callback for "Recent Logs" and left-click.
        on_settings: Callback for "Settings" menu item.
        on_exit: Callback for "Exit" menu item.

    Returns:
        pystray.Icon instance (not yet running).
    """
    # Load icon image
    try:
        image = Image.open(str(ICON_PATH))
    except Exception as exc:
        logger.warning("Failed to load icon from %s: %s", ICON_PATH, exc)
        # Create a simple fallback icon
        image = Image.new("RGB", (64, 64), color=(0, 240, 255))

    menu = Menu(
        MenuItem(
            f"⚡ Sync Now  (Ctrl+Shift+L)",
            lambda: on_sync(),
        ),
        Menu.SEPARATOR,
        MenuItem(
            "📋 Recent Logs",
            lambda: on_logs(),
        ),
        MenuItem(
            "⚙️ Settings",
            lambda: on_settings(),
        ),
        Menu.SEPARATOR,
        MenuItem(
            f"ℹ️ {APP_NAME} v{APP_VERSION}",
            lambda: None,
            enabled=False,
        ),
        Menu.SEPARATOR,
        MenuItem(
            "❌ Exit",
            lambda: on_exit(),
        ),
    )

    icon = Icon(
        name=APP_NAME,
        icon=image,
        title=f"{APP_NAME} — Ready",
        menu=menu,
    )

    # Left-click handler: open logs
    def on_click(icon_instance, item):
        """Handle left-click on the tray icon."""
        on_logs()

    # Note: pystray doesn't have a native left-click handler on Windows,
    # but the default action (first menu item or title click) can be
    # configured by making the first item the default
    icon.menu = Menu(
        MenuItem(
            f"⚡ Sync Now  (Ctrl+Shift+L)",
            lambda: on_sync(),
            default=True,  # Double-click triggers this
        ),
        Menu.SEPARATOR,
        MenuItem(
            "📋 Recent Logs",
            lambda: on_logs(),
        ),
        MenuItem(
            "⚙️ Settings",
            lambda: on_settings(),
        ),
        Menu.SEPARATOR,
        MenuItem(
            f"ℹ️ {APP_NAME} v{APP_VERSION}",
            lambda: None,
            enabled=False,
        ),
        Menu.SEPARATOR,
        MenuItem(
            "❌ Exit",
            lambda: on_exit(),
        ),
    )

    return icon


def run_tray(icon: Icon) -> None:
    """
    Run the tray icon. This is a BLOCKING call that keeps
    the app alive until the user clicks Exit.

    Args:
        icon: pystray.Icon instance from create_tray().
    """
    logger.info("System tray icon started. %s is ready.", APP_NAME)
    icon.run()


def update_tray_title(icon: Icon, title: str) -> None:
    """
    Update the tray icon hover title text.

    Args:
        icon: The running tray icon.
        title: New title text (shown on hover).
    """
    icon.title = title
