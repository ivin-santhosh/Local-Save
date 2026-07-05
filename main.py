"""
LinkSync AI — Main Entry Point (Run-Once Mode)
=================================================
The agent runs ONLY when invoked and exits completely after.

Flow:
  1. User double-clicks "LinkSync AI" shortcut on desktop
  2. App launches → immediately captures browser tabs
  3. Tab selector appears (foreground, topmost)
  4. User selects tabs → clicks PROCEED
  5. Ollama starts → pipeline runs → dispatch → Ollama stops
  6. Final report appears with OK button
  7. User clicks OK → FULL SHUTDOWN (zero processes left)

No tray icon. No background listeners. No wasted RAM.
The agent exists ONLY while it's doing work.
"""

import logging
import sys
import threading
import time
from pathlib import Path

# ── Ensure project root is on the Python path ──
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ── Fix console encoding (Windows cp1252 → UTF-8) ──
# Prevents UnicodeEncodeError when logging emoji characters
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass  # Gracefully ignore if reconfiguration fails

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
logger.info("=== %s v%s — Session Start ===", APP_NAME, APP_VERSION)

# ── CustomTkinter root ──
import customtkinter as ctk

ctk.set_appearance_mode("dark")
_root = ctk.CTk()
_root.withdraw()  # Hidden root — we use CTkToplevels


def _run_first_time_setup() -> None:
    """
    Run the first-time bootstrap with the progress UI.

    Runs SYNCHRONOUSLY on the main thread to avoid Python 3.14's
    strict Tkinter threading rules. Each bootstrap step updates
    the UI directly via _root.update().
    """
    from src.bootstrap.first_run import is_first_run, run_bootstrap

    if not is_first_run():
        return

    logger.info("First run detected — starting bootstrap...")
    from src.ui.progress_window import BootstrapProgressWindow

    progress = BootstrapProgressWindow(_root)
    _root.update()  # Render the window

    def _callback(step: int, success: bool, detail: str):
        """Called by bootstrap for each step — runs on main thread."""
        icon = '✅' if success else '❌'
        progress.update_step_direct(step, success, detail)
        progress.add_log_direct(f"{icon} Step {step}: {detail}")
        _root.update()  # Process UI events after each step

    run_bootstrap(progress_callback=_callback)

    # Show completion
    progress.add_log_direct("\n✅ Setup complete! LinkSync AI is ready.")
    progress.protocol("WM_DELETE_WINDOW", progress.destroy)
    _root.update()

    # Brief pause to let user see completion
    import time
    end = time.time() + 2.0
    while time.time() < end:
        try:
            _root.update()
        except Exception:
            break
        time.sleep(0.05)

    try:
        progress.destroy()
    except Exception:
        pass


def _initialize_storage() -> None:
    """Initialize the database and vector store."""
    try:
        from src.storage.database import init_db
        init_db()
    except Exception as exc:
        logger.error("Database init failed: %s", exc)

    try:
        from src.storage.vector_store import init_vector_store
        init_vector_store()
    except Exception as exc:
        logger.error("Vector store init failed: %s", exc)


def _full_shutdown(exit_code: int = 0) -> None:
    """
    Complete, clean shutdown. Kills EVERYTHING we started.
    After this call, zero LinkSync processes remain.
    """
    logger.info("Full shutdown initiated...")

    # Stop Ollama (if we started it)
    try:
        from src.brain.ollama_manager import force_shutdown
        force_shutdown()
    except Exception:
        pass

    # Close Playwright browser
    try:
        from src.scraper.page_scraper import close_browser
        close_browser()
    except Exception:
        pass

    # Close database
    try:
        from src.storage.database import close_db
        close_db()
    except Exception:
        pass

    logger.info("=== %s — Session End ===", APP_NAME)

    # Kill the Tkinter loop and exit the process
    try:
        _root.quit()
        _root.destroy()
    except Exception:
        pass

    sys.exit(exit_code)


def _start_sync_cycle() -> None:
    """
    The main (and only) sync cycle. Captures tabs, shows UI,
    processes, dispatches, shows report, then exits on OK.
    """
    from src.capture.tab_capture import capture_tabs

    # ── Capture tabs from the foreground browser ──
    browser_name, tabs = capture_tabs()

    if not tabs:
        logger.info("No tabs captured.")
        _show_no_tabs_dialog()
        return

    logger.info("Captured %d tabs from %s.", len(tabs), browser_name)

    # ── Show tab selector ──
    from src.ui.tab_selector import TabSelectorWindow

    def _on_proceed(selected_tabs: list[dict]):
        """Process selected tabs (background thread)."""
        from src.brain.ollama_manager import ollama_session
        from src.brain.graph import run_sync_pipeline
        from src.dispatch.dispatcher import dispatch_batch

        start_time = time.time()

        # ── Ollama runs ONLY during this block ──
        with ollama_session() as ollama_ready:
            if not ollama_ready:
                logger.warning("Ollama unavailable. Trying API fallback.")

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

        # ── Ollama stopped. RAM freed. ──
        logger.info("Ollama released.")

        # Generate combined report and save it locally
        try:
            from src.ui.report_generator import generate_report
            report_path = generate_report(results)
            logger.info("Sync report generated at: %s", report_path)

            # Send combined report to WhatsApp "ME" group
            try:
                from src.dispatch.dispatcher import dispatch_summary
                report_content = report_path.read_text(encoding="utf-8")
                max_chars = 4000
                truncated_content = report_content[:max_chars]
                if len(report_content) > max_chars:
                    truncated_content += "\n\n... (Report truncated due to length)"
                
                # Send stats-only title card to dispatcher
                dispatch_summary(url="Local Report Path: " + str(report_path), summary=truncated_content, group_name="ME")
            except Exception as exc:
                logger.error("Failed to dispatch combined report to WhatsApp: %s", exc)

            # Open report file locally
            try:
                os.startfile(str(report_path))
            except Exception as exc:
                logger.error("Failed to open report file locally: %s", exc)

        except Exception as exc:
            logger.error("Failed during report generation phase: %s", exc)

        # Show final report (OK button triggers full shutdown)
        elapsed = time.time() - start_time
        selector.show_final_report(
            results, elapsed,
            on_ok=_full_shutdown,  # ← THIS is the key: OK = exit everything
        )

        # Store sync in context
        try:
            from src.storage.context_manager import record_sync
            record_sync(f"batch_{len(results)}_tabs")
        except Exception:
            pass

    def _on_cancel():
        """User closed the selector without proceeding."""
        _full_shutdown()

    selector = TabSelectorWindow(
        _root,
        tabs=tabs,
        browser_name=browser_name,
        on_proceed=_on_proceed,
        on_cancel=_on_cancel,
    )


def _show_no_tabs_dialog() -> None:
    """Show a brief 'no tabs found' message, then exit."""
    dialog = ctk.CTkToplevel(_root)
    dialog.title(f"🔗 {APP_NAME}")
    dialog.geometry("400x200")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.configure(fg_color="#0a0e1a")

    # Center on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - 400) // 2
    y = (dialog.winfo_screenheight() - 200) // 2
    dialog.geometry(f"+{x}+{y}")

    ctk.CTkLabel(
        dialog,
        text="No browser tabs detected",
        font=("Segoe UI", 18, "bold"),
        text_color="#00f0ff",
    ).pack(pady=(30, 10))

    ctk.CTkLabel(
        dialog,
        text="Make sure a browser is in the foreground\nbefore launching LinkSync AI.",
        font=("Segoe UI", 12),
        text_color="#94a3b8",
    ).pack(pady=5)

    ctk.CTkButton(
        dialog,
        text="OK",
        width=120, height=36,
        fg_color="#00f0ff",
        text_color="#0a0e1a",
        hover_color="#39ff14",
        font=("Segoe UI", 14, "bold"),
        command=_full_shutdown,
    ).pack(pady=20)

    dialog.protocol("WM_DELETE_WINDOW", _full_shutdown)


# ============================================================
# Entry Point
# ============================================================

def main() -> None:
    """
    Main entry point. Runs the full lifecycle ONCE:
    bootstrap → capture → select → process → report → exit.
    """
    try:
        # Phase 1: First-run setup (if needed)
        _run_first_time_setup()

        # Phase 2: Initialize storage
        _initialize_storage()

        # Phase 3: Start the sync cycle immediately
        #   (scheduled with after() so the Tk mainloop is running)
        _root.after(100, _start_sync_cycle)

        # Phase 4: Run the Tkinter event loop
        #   (keeps windows alive until _full_shutdown() is called)
        _root.mainloop()

    except KeyboardInterrupt:
        _full_shutdown()
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        _full_shutdown(1)


if __name__ == "__main__":
    main()
