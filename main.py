"""
LinkSync AI — Main Entry Point
=================================
This is the file that runs when the user double-clicks
LinkSync_AI.bat. It orchestrates:

1. First-run bootstrap (if needed)
2. Database & vector store initialization
3. Global hotkey listener
4. System tray icon
5. Sync cycle on hotkey press

Ollama Lifecycle:
  Ollama is NOT kept running 24/7. It starts only when a sync
  cycle begins (hotkey press → pipeline runs) and stops after
  dispatch completes. If Ollama was already running (e.g., another
  AI agent), we don't touch it.

The tray icon runs on the main thread (blocking).
Everything else runs on daemon threads.
"""

import logging
import sys
import threading
import time
from pathlib import Path

# ── Ensure project root is on the Python path ──
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ── Logging setup ──
from config import APP_NAME, APP_VERSION, DATA_DIR

LOG_FILE = DATA_DIR / "linksync.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(APP_NAME)
logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

# ── CustomTkinter root (hidden, for window management) ──
import customtkinter as ctk

ctk.set_appearance_mode("dark")
_root = ctk.CTk()
_root.withdraw()  # Hidden root window — we use CTkToplevels


def _run_first_time_setup() -> None:
    """Run the first-time bootstrap with the progress UI."""
    from src.bootstrap.first_run import is_first_run, run_bootstrap

    if not is_first_run():
        logger.info("Not first run — skipping bootstrap.")
        return

    logger.info("First run detected — starting bootstrap...")
    from src.ui.progress_window import BootstrapProgressWindow

    progress = BootstrapProgressWindow(_root)

    def _bootstrap_thread():
        def _callback(step: int, success: bool, detail: str):
            progress.update_step(step, success, detail)
            progress.add_log(f"{'✅' if success else '❌'} Step {step}: {detail}")

        run_bootstrap(progress_callback=_callback)
        progress.complete()

    threading.Thread(target=_bootstrap_thread, daemon=True).start()

    # Wait for the progress window to close
    progress.wait_window()


def _initialize_storage() -> None:
    """Initialize the database and vector store."""
    try:
        from src.storage.database import init_db
        init_db()
        logger.info("Database initialized.")
    except Exception as exc:
        logger.error("Database init failed: %s", exc)

    try:
        from src.storage.vector_store import init_vector_store
        init_vector_store()
        logger.info("Vector store initialized.")
    except Exception as exc:
        logger.error("Vector store init failed: %s", exc)


def _on_hotkey_pressed() -> None:
    """
    Called when the user presses the global hotkey.
    Runs the full sync cycle: capture → select → process → dispatch.
    """
    logger.info("Hotkey pressed! Starting sync cycle...")

    # Schedule UI work on the main thread
    _root.after(0, _start_sync_cycle)


def _start_sync_cycle() -> None:
    """Start the sync cycle on the main thread (for UI)."""
    from src.capture.tab_capture import capture_tabs

    # Capture tabs
    browser_name, tabs = capture_tabs()

    if not tabs:
        logger.info("No tabs captured. Showing notification.")
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                APP_NAME,
                "No browser tabs detected. Make sure a browser is in the foreground.",
                duration=4,
                threaded=True,
            )
        except Exception:
            pass
        return

    logger.info("Captured %d tabs from %s.", len(tabs), browser_name)

    # Show tab selector
    from src.ui.tab_selector import TabSelectorWindow

    def _on_proceed(selected_tabs: list[dict]):
        """Process selected tabs (runs on background thread)."""
        from src.brain.ollama_manager import ollama_session
        from src.brain.graph import run_sync_pipeline
        from src.dispatch.dispatcher import dispatch_batch

        start_time = time.time()

        # ── Start Ollama only for this sync cycle ──
        with ollama_session() as ollama_ready:
            if not ollama_ready:
                logger.warning("Ollama not available. Will try API fallback.")

            # Run the pipeline
            def _progress(index: int, icon: str, text: str):
                selector.update_tab_status(
                    index, icon, text,
                    title=selected_tabs[index].get("title", ""),
                )
                selector.update_progress((index + 1) / len(selected_tabs))

            results = run_sync_pipeline(selected_tabs, _progress)

            # Update provider display
            providers_used = set(r.get("provider_used", "") for r in results)
            providers_used.discard("none")
            if providers_used:
                selector.update_provider(", ".join(providers_used))

            # Dispatch to WhatsApp
            def _dispatch_progress(index: int, status: str):
                selector.update_tab_status(
                    index, "📤" if "Sent" in status else "❌",
                    status,
                    title=selected_tabs[index].get("title", ""),
                )

            results = dispatch_batch(results, progress_callback=_dispatch_progress)

        # ── Ollama stopped here (if we started it) ──
        logger.info("Ollama released after sync cycle.")

        # Show final report
        elapsed = time.time() - start_time
        selector.show_final_report(results, elapsed)

        # Store sync in context
        try:
            from src.storage.context_manager import record_sync
            record_sync(f"batch_{len(results)}_tabs")
        except Exception:
            pass

    selector = TabSelectorWindow(
        _root,
        tabs=tabs,
        browser_name=browser_name,
        on_proceed=_on_proceed,
    )


def _on_open_logs() -> None:
    """Open the logs window from tray menu."""
    _root.after(0, _show_logs)


def _show_logs() -> None:
    from src.ui.logs_window import LogsWindow
    LogsWindow(_root)


def _on_open_settings() -> None:
    """Open the settings dialog from tray menu."""
    _root.after(0, _show_settings)


def _show_settings() -> None:
    from src.ui.settings_dialog import SettingsDialog
    SettingsDialog(_root)


def _on_exit() -> None:
    """Clean shutdown."""
    logger.info("Shutting down %s...", APP_NAME)

    from src.hotkey.global_hotkey import stop_listener
    stop_listener()

    # Force-stop Ollama if we started it
    try:
        from src.brain.ollama_manager import force_shutdown
        force_shutdown()
    except Exception:
        pass

    try:
        from src.scraper.page_scraper import close_browser
        close_browser()
    except Exception:
        pass

    try:
        from src.storage.database import close_db
        close_db()
    except Exception:
        pass

    if _tray_icon:
        _tray_icon.stop()

    _root.quit()
    logger.info("%s stopped.", APP_NAME)


# ============================================================
# Application Lifecycle
# ============================================================

_tray_icon = None


def main() -> None:
    """Main application entry point."""
    global _tray_icon

    try:
        # Phase 1: First-run setup (if needed)
        _run_first_time_setup()

        # Phase 2: Initialize storage
        _initialize_storage()

        # Phase 3: Start hotkey listener
        from src.hotkey.global_hotkey import start_listener, get_active_hotkey_display
        start_listener(callback=_on_hotkey_pressed)
        logger.info("Hotkey listener active: %s", get_active_hotkey_display())

        # Phase 4: Create and run system tray
        from src.tray.system_tray import create_tray, run_tray

        _tray_icon = create_tray(
            on_sync=_on_hotkey_pressed,
            on_logs=_on_open_logs,
            on_settings=_on_open_settings,
            on_exit=_on_exit,
        )

        # Run tray in a separate thread so the Tkinter mainloop can run
        tray_thread = threading.Thread(target=run_tray, args=(_tray_icon,), daemon=True)
        tray_thread.start()

        # Show startup notification
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                APP_NAME,
                f"Ready! Press {get_active_hotkey_display()} to sync.",
                duration=3,
                threaded=True,
            )
        except Exception:
            pass

        # Run the Tkinter main loop (keeps windows alive)
        _root.mainloop()

    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
