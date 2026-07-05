"""
LinkSync AI — Tab Selector Window
====================================
The hero UI of the application. A cybersecurity-themed dark
popup that appears when the user presses Ctrl+Shift+L.

Flow:
  1. Shows all browser tabs with checkboxes
  2. Blacklisted tabs are greyed out with 🔒 icon
  3. User selects tabs → clicks PROCEED (or presses Enter)
  4. View transitions to live progress feed
  5. Final report with stats

Uses CustomTkinter for modern, dark-themed widgets.
"""

import logging
import threading
from typing import Callable, Optional
from urllib.parse import urlparse

import customtkinter as ctk

from src.ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_HOVER,
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    FONT_HEADING, FONT_HEADING_SM, FONT_BODY, FONT_BODY_SM,
    FONT_MONO_SM, FONT_CAPTION,
    PAD_SM, PAD_MD, PAD_LG, PAD_XL, PAD_XXL,
    SELECTOR_WIDTH, SELECTOR_HEIGHT,
    ICON_SUCCESS, ICON_FAIL, ICON_PENDING, ICON_PROCESSING,
    ICON_LOCK, ICON_LINK,
    BORDER_RADIUS,
)
from config import BLACKLISTED_DOMAINS, APP_NAME

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")


class TabSelectorWindow(ctk.CTkToplevel):
    """
    Modal popup for selecting browser tabs to sync.

    Displays all detected tabs with checkboxes. Blacklisted
    domains are shown greyed out and disabled. After the user
    clicks PROCEED, transitions to a progress view showing
    real-time processing status.
    """

    def __init__(
        self,
        master: Optional[ctk.CTk],
        tabs: list[dict],
        browser_name: str = "Browser",
        on_proceed: Optional[Callable[[list[dict]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """
        Args:
            master: Parent window (can be None for standalone).
            tabs: List of tab dicts with 'title', 'url', 'domain'.
            browser_name: Name of the detected browser.
            on_proceed: Callback with selected tabs when user clicks Proceed.
            on_cancel: Callback when user cancels/closes.
        """
        super().__init__(master)

        self.tabs = tabs
        self.browser_name = browser_name
        self._on_proceed = on_proceed
        self._on_cancel = on_cancel
        self._checkboxes: list[tuple[ctk.CTkCheckBox, ctk.BooleanVar, dict]] = []
        self._status_labels: list[ctk.CTkLabel] = []

        # Window setup
        self.title(f"{ICON_LINK} {APP_NAME}")
        self.geometry(f"{SELECTOR_WIDTH}x{SELECTOR_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG_PRIMARY)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - SELECTOR_WIDTH) // 2
        y = (self.winfo_screenheight() - SELECTOR_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

        # Bind Enter key
        self.bind("<Return>", lambda e: self._handle_proceed())

        # Build the selection view
        self._build_selection_view()

    def _build_selection_view(self) -> None:
        """Build the tab selection interface with checkboxes grouped by browser+window."""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)

        title_label = ctk.CTkLabel(
            header_frame,
            text=f"{ICON_LINK} LINKSYNC AI — Tab Selector",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        )
        title_label.pack(padx=PAD_XL, pady=(PAD_LG, PAD_SM))

        browser_label = ctk.CTkLabel(
            header_frame,
            text=f"{self.browser_name}  •  {len(self.tabs)} tabs detected",
            font=FONT_BODY_SM,
            text_color=TEXT_SECONDARY,
        )
        browser_label.pack(padx=PAD_XL, pady=(0, PAD_MD))

        # Scrollable checkbox area
        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=BG_PRIMARY,
            scrollbar_button_color=ACCENT_CYAN,
            scrollbar_button_hover_color=ACCENT_GREEN,
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_SM)

        # Group tabs by browser + window
        groups = {}
        for tab in self.tabs:
            browser = tab.get("browser", self.browser_name)
            window_idx = tab.get("window_index")
            if window_idx:
                key = f"{browser} — Window {window_idx}"
            else:
                key = browser
            
            if key not in groups:
                groups[key] = []
            groups[key].append(tab)

        # Create checkboxes grouped under section headers with master checkboxes
        for group_title, group_tabs in groups.items():
            group_header_frame = ctk.CTkFrame(
                self._scroll_frame,
                fg_color="transparent",
            )
            group_header_frame.pack(fill="x", padx=PAD_SM, pady=(PAD_MD, 2))

            group_vars = []
            group_var = ctk.BooleanVar(value=True)

            def make_toggle_cmd(g_var, g_vars):
                def toggle():
                    val = g_var.get()
                    for v in g_vars:
                        v.set(val)
                    self._update_counter()
                return toggle

            group_cb = ctk.CTkCheckBox(
                group_header_frame,
                text=f"📂 {group_title.upper()} ({len(group_tabs)} TABS)",
                variable=group_var,
                font=FONT_HEADING_SM,
                text_color=ACCENT_CYAN,
                fg_color=ACCENT_CYAN,
                hover_color=ACCENT_GREEN,
                checkmark_color=BG_PRIMARY,
                border_color=ACCENT_CYAN,
                command=make_toggle_cmd(group_var, group_vars),
            )
            group_cb.pack(side="left", padx=PAD_SM)

            for tab in group_tabs:
                var = self._add_tab_checkbox(tab)
                domain = tab.get("domain", "")
                url = tab.get("url", "")
                if not self._is_blacklisted(url, domain):
                    group_vars.append(var)

            # Sync initial master checkbox value
            all_checked = all(v.get() for v in group_vars) if group_vars else False
            group_var.set(all_checked)

        # Bottom bar
        bottom_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        bottom_frame.pack(fill="x", side="bottom", padx=0, pady=0)

        # Select All button
        self._select_all_btn = ctk.CTkButton(
            bottom_frame,
            text="SELECT ALL",
            width=120,
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=ACCENT_CYAN,
            text_color=ACCENT_CYAN,
            hover_color=BG_HOVER,
            font=FONT_BODY_SM,
            command=self._toggle_select_all,
        )
        self._select_all_btn.pack(side="left", padx=PAD_LG, pady=PAD_MD)

        # Counter label
        self._counter_label = ctk.CTkLabel(
            bottom_frame,
            text=self._get_counter_text(),
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        )
        self._counter_label.pack(side="left", padx=PAD_MD, pady=PAD_MD)

        # Proceed button
        self._proceed_btn = ctk.CTkButton(
            bottom_frame,
            text="▶  PROCEED",
            width=140,
            height=36,
            fg_color=ACCENT_CYAN,
            text_color=BG_PRIMARY,
            hover_color=ACCENT_GREEN,
            font=FONT_HEADING_SM,
            command=self._handle_proceed,
        )
        self._proceed_btn.pack(side="right", padx=PAD_LG, pady=PAD_MD)

    def _add_tab_checkbox(self, tab: dict) -> ctk.BooleanVar:
        """Add a single tab checkbox to the scrollable frame and return its variable."""
        domain = tab.get("domain", "")
        title = tab.get("title", "Untitled")
        url = tab.get("url", "")
        is_blacklisted = self._is_blacklisted(url, domain)

        # Frame for each tab entry
        entry_frame = ctk.CTkFrame(
            self._scroll_frame,
            fg_color=BG_TERTIARY,
            corner_radius=8,
        )
        entry_frame.pack(fill="x", padx=PAD_SM, pady=3)

        var = ctk.BooleanVar(value=not is_blacklisted)

        # Display text
        if is_blacklisted:
            display = f"{ICON_LOCK}  [{domain}] — {title[:50]}"
            text_color = TEXT_MUTED
        else:
            display = f"[{domain}] — {title[:50]}" if domain else title[:60]
            text_color = TEXT_PRIMARY

        cb = ctk.CTkCheckBox(
            entry_frame,
            text=display,
            variable=var,
            font=FONT_BODY_SM,
            text_color=text_color,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_GREEN,
            checkmark_color=BG_PRIMARY,
            border_color=ACCENT_CYAN if not is_blacklisted else TEXT_MUTED,
            command=self._update_counter,
        )
        cb.pack(padx=PAD_MD, pady=PAD_SM, anchor="w")

        if is_blacklisted:
            cb.configure(state="disabled")
            var.set(False)

        self._checkboxes.append((cb, var, tab))
        return var

    def _is_blacklisted(self, url: str, domain: str) -> bool:
        """Check if a URL/domain matches the blacklist."""
        url_lower = url.lower()
        domain_lower = domain.lower()
        for pattern in BLACKLISTED_DOMAINS:
            pattern_lower = pattern.lower()
            if "://" in pattern and url_lower.startswith(pattern_lower):
                return True
            if pattern_lower in domain_lower or pattern_lower in url_lower:
                return True
        return False

    def _get_selected_tabs(self) -> list[dict]:
        """Return list of tabs where checkbox is checked."""
        return [tab for _, var, tab in self._checkboxes if var.get()]

    def _get_counter_text(self) -> str:
        """Get the '3 of 7 selected' counter text."""
        selected = sum(1 for _, var, _ in self._checkboxes if var.get())
        total = len(self._checkboxes)
        return f"{selected} of {total} selected"

    def _update_counter(self) -> None:
        """Update the counter label after a checkbox change."""
        if hasattr(self, "_counter_label"):
            self._counter_label.configure(text=self._get_counter_text())

    def _toggle_select_all(self) -> None:
        """Toggle all non-blacklisted checkboxes."""
        selected = self._get_selected_tabs()
        selectable = [
            (cb, var, tab) for cb, var, tab in self._checkboxes
            if cb.cget("state") != "disabled"
        ]

        select_all = len(selected) < len(selectable)
        for _, var, _ in selectable:
            var.set(select_all)
        self._update_counter()

    def _handle_proceed(self) -> None:
        """Handle the Proceed button click."""
        selected = self._get_selected_tabs()
        if not selected:
            return

        logger.info("User selected %d tabs for sync.", len(selected))

        if self._on_proceed:
            # Transition to progress view
            self.show_progress_view(len(selected))
            # Run processing in background thread
            threading.Thread(
                target=self._on_proceed,
                args=(selected,),
                daemon=True,
            ).start()

    def _handle_close(self) -> None:
        """Handle window close."""
        if self._on_cancel:
            self._on_cancel()
        self.destroy()

    # ============================================================
    # Progress View
    # ============================================================

    def show_progress_view(self, tab_count: int) -> None:
        """
        Replace the selection view with a live progress feed.

        Args:
            tab_count: Number of tabs being processed.
        """
        # Clear existing content
        for widget in self.winfo_children():
            widget.destroy()

        self._status_labels = []

        # Header
        header_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        header_frame.pack(fill="x")

        ctk.CTkLabel(
            header_frame,
            text=f"{ICON_PROCESSING}  Processing {tab_count} tabs...",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        ).pack(padx=PAD_XL, pady=PAD_LG)

        # Status list
        self._progress_scroll = ctk.CTkScrollableFrame(
            self, fg_color=BG_PRIMARY,
        )
        self._progress_scroll.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_SM)

        # Create placeholder rows
        for i in range(tab_count):
            row = ctk.CTkFrame(self._progress_scroll, fg_color=BG_TERTIARY, corner_radius=8)
            row.pack(fill="x", padx=PAD_SM, pady=3)

            label = ctk.CTkLabel(
                row,
                text=f"{ICON_PENDING}  Tab {i + 1}  —  Queued",
                font=FONT_BODY_SM,
                text_color=TEXT_SECONDARY,
                anchor="w",
            )
            label.pack(padx=PAD_MD, pady=PAD_SM, fill="x")
            self._status_labels.append(label)

        # Progress bar
        self._progress_bar = ctk.CTkProgressBar(
            self,
            fg_color=BG_TERTIARY,
            progress_color=ACCENT_CYAN,
            height=8,
        )
        self._progress_bar.pack(fill="x", padx=PAD_XL, pady=PAD_MD)
        self._progress_bar.set(0)

        # Provider label
        self._provider_label = ctk.CTkLabel(
            self,
            text="Provider: waiting...",
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        )
        self._provider_label.pack(padx=PAD_XL, pady=(0, PAD_MD))

    def update_tab_status(
        self, index: int, icon: str, text: str, title: str = ""
    ) -> None:
        """
        Update a specific tab's status in the progress view.

        Thread-safe: uses after() to update from any thread.

        Args:
            index: Tab index (0-based).
            icon: Status icon (✅, ❌, ⏳, 🧠).
            text: Status text (e.g., "Summarized", "Skipped").
            title: Optional tab title to display.
        """
        def _update():
            if index < len(self._status_labels):
                display = f"{icon}  {title[:35]}  —  {text}" if title else f"{icon}  Tab {index + 1}  —  {text}"
                self._status_labels[index].configure(
                    text=display,
                    text_color=TEXT_PRIMARY if icon == ICON_SUCCESS else TEXT_SECONDARY,
                )
        self.after(0, _update)

    def update_progress(self, percentage: float) -> None:
        """Update the progress bar (0.0 to 1.0). Thread-safe."""
        self.after(0, lambda: self._progress_bar.set(percentage))

    def update_provider(self, provider: str) -> None:
        """Update the provider display label. Thread-safe."""
        self.after(
            0,
            lambda: self._provider_label.configure(
                text=f"Provider: {provider}"
            ),
        )

    # ============================================================
    # Final Report
    # ============================================================

    def show_final_report(
        self,
        results: list[dict],
        elapsed: float = 0,
        on_ok: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Show a DETAILED completion report with per-tab summaries.

        Each tab gets a card showing:
        - Title & domain
        - Full summary text (what the LLM produced)
        - Dispatch status (sent/failed/skipped)

        Thread-safe: call from any thread.

        Args:
            results: List of result dicts from the pipeline.
            elapsed: Total processing time in seconds.
            on_ok: Callback when user clicks OK. Triggers full app shutdown.
        """
        self._on_ok = on_ok

        def _show():
            for widget in self.winfo_children():
                widget.destroy()

            # Make window taller for detailed report
            self.geometry(f"{SELECTOR_WIDTH}x{SELECTOR_HEIGHT + 100}")

            # Wire window close to full shutdown too
            self.protocol("WM_DELETE_WINDOW", self._handle_ok)

            summarized = sum(1 for r in results if r.get("status") == "summarized")
            dispatched = sum(1 for r in results if r.get("dispatched"))
            skipped = sum(1 for r in results if r.get("status") in ("aborted", "skipped", "blacklisted"))
            failed = sum(1 for r in results if r.get("status") == "failed")
            total = len(results)

            # ── Header ──
            header = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
            header.pack(fill="x")

            ctk.CTkLabel(
                header,
                text=f"{ICON_SUCCESS}  SYNC COMPLETE",
                font=FONT_HEADING,
                text_color=ACCENT_GREEN,
            ).pack(padx=PAD_XL, pady=(PAD_LG, PAD_SM))

            # Stats row
            stats_text = f"✅ {summarized} summarized  •  📤 {dispatched} sent"
            if skipped > 0:
                stats_text += f"  •  ⏭ {skipped} skipped"
            if failed > 0:
                stats_text += f"  •  ❌ {failed} failed"
            if elapsed > 0:
                stats_text += f"  •  ⏱ {elapsed:.1f}s"

            ctk.CTkLabel(
                header,
                text=stats_text,
                font=FONT_BODY_SM,
                text_color=TEXT_SECONDARY,
            ).pack(padx=PAD_XL, pady=(0, PAD_MD))

            # ── Per-Tab Detail Cards (scrollable) ──
            scroll = ctk.CTkScrollableFrame(
                self,
                fg_color=BG_PRIMARY,
                scrollbar_button_color=ACCENT_CYAN,
                scrollbar_button_hover_color=ACCENT_GREEN,
            )
            scroll.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_SM)

            for i, result in enumerate(results):
                self._build_result_card(scroll, i, result)

            # ── Bottom Bar ──
            ctk.CTkLabel(
                self,
                text="Review your summaries above. Press OK to exit cleanly.",
                font=FONT_CAPTION,
                text_color=TEXT_MUTED,
            ).pack(padx=PAD_XL, pady=(PAD_SM, 0))

            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=PAD_XL, pady=(PAD_SM, PAD_LG))

            ctk.CTkButton(
                btn_frame,
                text="📋 VIEW LOGS",
                width=130,
                fg_color="transparent",
                border_width=1,
                border_color=ACCENT_CYAN,
                text_color=ACCENT_CYAN,
                hover_color=BG_HOVER,
                font=FONT_BODY_SM,
                command=self._open_logs,
            ).pack(side="left", padx=PAD_SM)

            ctk.CTkButton(
                btn_frame,
                text="✅  OK",
                width=140,
                height=40,
                fg_color=ACCENT_GREEN,
                text_color=BG_PRIMARY,
                hover_color=ACCENT_CYAN,
                font=FONT_HEADING_SM,
                command=self._handle_ok,
            ).pack(side="right", padx=PAD_SM)

            # Bind Enter key to OK
            self.bind("<Return>", lambda e: self._handle_ok())

        self.after(0, _show)

    def _build_result_card(
        self, parent: ctk.CTkScrollableFrame, index: int, result: dict
    ) -> None:
        """
        Build a single tab result card showing title, summary, and status.

        Args:
            parent: The scrollable frame to add the card to.
            index: Tab index (for numbering).
            result: Result dict from the pipeline with keys like
                    title, url, domain, summary, status, dispatched.
        """
        status = result.get("status", "unknown")
        title = result.get("title", "Untitled")[:60]
        domain = result.get("domain", "")
        url = result.get("url", "")
        summary = result.get("summary", "")
        browser = result.get("browser", "")
        dispatched = result.get("dispatched", False)

        # Status icon and color
        if status == "summarized" and dispatched:
            icon = "📤"
            border_color = ACCENT_GREEN
        elif status == "summarized":
            icon = ICON_SUCCESS
            border_color = ACCENT_CYAN
        elif status in ("aborted", "blacklisted"):
            icon = ICON_LOCK
            border_color = TEXT_MUTED
        elif status == "skipped":
            icon = "⏭"
            border_color = ACCENT_YELLOW
        else:
            icon = ICON_FAIL
            border_color = ACCENT_RED

        # Card frame
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_TERTIARY,
            corner_radius=10,
            border_width=1,
            border_color=border_color,
        )
        card.pack(fill="x", padx=PAD_SM, pady=4)

        # Title row: icon + title + browser badge
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.pack(fill="x", padx=PAD_MD, pady=(PAD_SM, 0))

        title_text = f"{icon}  {title}"
        if browser:
            title_text += f"  [{browser}]"

        ctk.CTkLabel(
            title_row,
            text=title_text,
            font=FONT_BODY_SM,
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Domain/URL
        if domain or url:
            display_url = domain or url[:50]
            ctk.CTkLabel(
                card,
                text=f"   🌐 {display_url}",
                font=FONT_CAPTION,
                text_color=ACCENT_CYAN,
                anchor="w",
            ).pack(fill="x", padx=PAD_MD, pady=(2, 0))

        # Summary text (the key content the user wants to see)
        if summary:
            summary_frame = ctk.CTkFrame(
                card, fg_color=BG_SECONDARY, corner_radius=6,
            )
            summary_frame.pack(fill="x", padx=PAD_MD, pady=(PAD_SM, PAD_SM))

            ctk.CTkLabel(
                summary_frame,
                text=summary,
                font=FONT_BODY_SM,
                text_color=TEXT_SECONDARY,
                anchor="nw",
                justify="left",
                wraplength=SELECTOR_WIDTH - 120,
            ).pack(padx=PAD_SM, pady=PAD_SM, fill="x")
        elif status in ("aborted", "blacklisted"):
            ctk.CTkLabel(
                card,
                text="   🔒 Skipped (blacklisted domain)",
                font=FONT_CAPTION,
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x", padx=PAD_MD, pady=(2, PAD_SM))
        elif status == "skipped":
            reason = result.get("skip_reason", "Content too short or duplicate")
            ctk.CTkLabel(
                card,
                text=f"   ⏭ Skipped: {reason}",
                font=FONT_CAPTION,
                text_color=ACCENT_YELLOW,
                anchor="w",
            ).pack(fill="x", padx=PAD_MD, pady=(2, PAD_SM))
        else:
            ctk.CTkLabel(
                card,
                text=f"   ❌ {status}",
                font=FONT_CAPTION,
                text_color=ACCENT_RED,
                anchor="w",
            ).pack(fill="x", padx=PAD_MD, pady=(2, PAD_SM))

    def _handle_ok(self) -> None:
        """Handle OK button — triggers full app shutdown."""
        if self._on_ok:
            self._on_ok()
        else:
            self.destroy()

    def _open_logs(self) -> None:
        """Open the logs window."""
        try:
            from src.ui.logs_window import LogsWindow
            LogsWindow(self)
        except Exception as exc:
            logger.error("Failed to open logs: %s", exc)
