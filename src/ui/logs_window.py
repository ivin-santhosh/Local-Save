"""
LinkSync AI — Recent Logs Window
==================================
Displays recent sync entries from the SQLite database.
Each entry shows timestamp, domain, summary, and status.
Users can mark entries as "Irrelevant" to train the
negative filter in ChromaDB.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import customtkinter as ctk

from src.ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_HOVER,
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    FONT_HEADING, FONT_BODY, FONT_BODY_SM, FONT_CAPTION, FONT_MONO_SM,
    PAD_SM, PAD_MD, PAD_LG, PAD_XL,
    LOGS_WIDTH, LOGS_HEIGHT,
    ICON_SUCCESS, ICON_FAIL, ICON_SKIP,
)
from config import APP_NAME

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")

_STATUS_STYLES = {
    "sent": (ICON_SUCCESS, ACCENT_GREEN, "Sent"),
    "summarized": (ICON_SUCCESS, ACCENT_GREEN, "Summarized"),
    "failed": (ICON_FAIL, ACCENT_RED, "Failed"),
    "skipped": (ICON_SKIP, TEXT_MUTED, "Skipped"),
    "irrelevant": ("🚫", TEXT_MUTED, "Irrelevant"),
    "pending": ("⏳", ACCENT_YELLOW, "Pending"),
}


class LogsWindow(ctk.CTkToplevel):
    """
    Window showing recent sync log entries.

    Features:
    - Dark themed with cybersecurity aesthetic
    - Each entry shows: timestamp, domain, summary (truncated), status
    - "Mark Irrelevant" button per entry
    - Refresh button to reload data
    """

    def __init__(self, master: Optional[ctk.CTk] = None):
        super().__init__(master)

        self.title(f"📋 {APP_NAME} — Recent Logs")
        self.geometry(f"{LOGS_WIDTH}x{LOGS_HEIGHT}")
        self.configure(fg_color=BG_PRIMARY)
        self.attributes("-topmost", True)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - LOGS_WIDTH) // 2
        y = (self.winfo_screenheight() - LOGS_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()
        self._load_logs()

    def _build_ui(self) -> None:
        """Build the logs window UI."""
        # Header
        header = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="📋  Recent Sync Logs",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        ).pack(side="left", padx=PAD_XL, pady=PAD_LG)

        self._count_label = ctk.CTkLabel(
            header,
            text="",
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        )
        self._count_label.pack(side="left", padx=PAD_SM, pady=PAD_LG)

        ctk.CTkButton(
            header,
            text="🔄 Refresh",
            width=100,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=ACCENT_CYAN,
            text_color=ACCENT_CYAN,
            hover_color=BG_HOVER,
            font=FONT_BODY_SM,
            command=self._load_logs,
        ).pack(side="right", padx=PAD_XL, pady=PAD_LG)

        # Scrollable log entries
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=BG_PRIMARY,
        )
        self._scroll.pack(fill="both", expand=True, padx=PAD_MD, pady=PAD_SM)

    def _load_logs(self) -> None:
        """Load and display recent logs from the database."""
        # Clear existing entries
        for widget in self._scroll.winfo_children():
            widget.destroy()

        try:
            from src.storage.database import get_recent_logs
            logs = get_recent_logs(limit=50)
        except Exception as exc:
            logger.error("Failed to load logs: %s", exc)
            ctk.CTkLabel(
                self._scroll,
                text=f"Error loading logs: {exc}",
                font=FONT_BODY,
                text_color=ACCENT_RED,
            ).pack(padx=PAD_LG, pady=PAD_XL)
            return

        self._count_label.configure(text=f"({len(logs)} entries)")

        if not logs:
            ctk.CTkLabel(
                self._scroll,
                text="No sync logs yet. Press Ctrl+Shift+L to sync!",
                font=FONT_BODY,
                text_color=TEXT_MUTED,
            ).pack(padx=PAD_LG, pady=PAD_XL)
            return

        for log in logs:
            self._add_log_entry(log)

    def _add_log_entry(self, log: dict) -> None:
        """Add a single log entry to the scroll frame."""
        entry = ctk.CTkFrame(
            self._scroll, fg_color=BG_TERTIARY, corner_radius=8,
        )
        entry.pack(fill="x", padx=PAD_SM, pady=3)

        # Top row: timestamp + domain + status
        top = ctk.CTkFrame(entry, fg_color="transparent")
        top.pack(fill="x", padx=PAD_MD, pady=(PAD_SM, 0))

        # Timestamp
        created = log.get("created_at", "")[:16]  # Trim to minute
        ctk.CTkLabel(
            top, text=created,
            font=FONT_MONO_SM, text_color=TEXT_MUTED,
        ).pack(side="left")

        # Domain
        url = log.get("url", "")
        domain = urlparse(url).netloc if url else "unknown"
        ctk.CTkLabel(
            top, text=f"  •  {domain}",
            font=FONT_BODY_SM, text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=PAD_SM)

        # Status badge
        status = log.get("status", "pending")
        icon, color, label = _STATUS_STYLES.get(
            status, ("?", TEXT_MUTED, status)
        )
        ctk.CTkLabel(
            top, text=f"{icon} {label}",
            font=FONT_CAPTION, text_color=color,
        ).pack(side="right")

        # Summary row
        summary = log.get("summary", "")
        if summary:
            truncated = summary[:100] + "..." if len(summary) > 100 else summary
            ctk.CTkLabel(
                entry, text=truncated,
                font=FONT_BODY_SM, text_color=TEXT_PRIMARY,
                anchor="w", wraplength=LOGS_WIDTH - 120,
            ).pack(padx=PAD_MD, pady=(PAD_SM, 0), fill="x")

        # Action row
        if status not in ("irrelevant",):
            action_frame = ctk.CTkFrame(entry, fg_color="transparent")
            action_frame.pack(fill="x", padx=PAD_MD, pady=(PAD_SM, PAD_SM))

            log_id = log.get("id")
            ctk.CTkButton(
                action_frame,
                text="Mark Irrelevant",
                width=120, height=26,
                fg_color="transparent",
                border_width=1,
                border_color=ACCENT_RED,
                text_color=ACCENT_RED,
                hover_color=BG_HOVER,
                font=FONT_CAPTION,
                command=lambda lid=log_id, u=url, s=summary: self._mark_irrelevant(lid, u, s),
            ).pack(side="right")

    def _mark_irrelevant(self, log_id: int, url: str, summary: str) -> None:
        """Mark a log entry as irrelevant and update the negative filter."""
        try:
            from src.storage.database import mark_irrelevant
            from src.storage.vector_store import add_to_negative_filter

            mark_irrelevant(log_id)
            add_to_negative_filter(url, summary)

            logger.info("Marked as irrelevant: %s", url)
            self._load_logs()  # Refresh view
        except Exception as exc:
            logger.error("Failed to mark irrelevant: %s", exc)
