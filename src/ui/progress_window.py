"""
LinkSync AI — Bootstrap Progress Window
==========================================
The first-run setup progress UI. Shows a step-by-step
checklist as the agent auto-installs dependencies,
discovers apps, and configures itself.
"""

import logging
from typing import Optional

import customtkinter as ctk

from src.ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY,
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    FONT_HEADING, FONT_BODY, FONT_BODY_SM, FONT_MONO_SM, FONT_CAPTION,
    PAD_SM, PAD_MD, PAD_LG, PAD_XL,
    PROGRESS_WIDTH, PROGRESS_HEIGHT,
    ICON_SUCCESS, ICON_FAIL, ICON_PENDING,
)
from config import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")

BOOTSTRAP_STEPS = [
    "Checking Python version",
    "Verifying dependencies",
    "Setting up Playwright",
    "Discovering browsers",
    "Discovering WhatsApp",
    "Checking Ollama",
    "Creating agent context",
    "Finalizing setup",
]


class BootstrapProgressWindow(ctk.CTkToplevel):
    """
    Progress window shown during first-run bootstrap.

    Displays each setup step with an icon that updates
    as steps complete (⏳ → ✅ or ❌). Includes a
    log output area at the bottom.
    """

    def __init__(self, master: Optional[ctk.CTk] = None):
        super().__init__(master)

        self.title(f"🚀 {APP_NAME} — First-Time Setup")
        self.geometry(f"{PROGRESS_WIDTH}x{PROGRESS_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG_PRIMARY)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent close during setup

        # Center
        self.update_idletasks()
        x = (self.winfo_screenwidth() - PROGRESS_WIDTH) // 2
        y = (self.winfo_screenheight() - PROGRESS_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

        self._step_labels: list[ctk.CTkLabel] = []
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the progress window UI."""
        # Header
        header = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text=f"🚀  Setting up {APP_NAME} v{APP_VERSION}",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        ).pack(padx=PAD_XL, pady=(PAD_LG, PAD_SM))

        ctk.CTkLabel(
            header,
            text="One-time setup — this won't happen again",
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        ).pack(padx=PAD_XL, pady=(0, PAD_MD))

        # Steps list
        steps_frame = ctk.CTkFrame(self, fg_color=BG_PRIMARY)
        steps_frame.pack(fill="x", padx=PAD_XL, pady=PAD_MD)

        for i, step_name in enumerate(BOOTSTRAP_STEPS):
            label = ctk.CTkLabel(
                steps_frame,
                text=f"{ICON_PENDING}  {step_name}",
                font=FONT_BODY_SM,
                text_color=TEXT_SECONDARY,
                anchor="w",
            )
            label.pack(fill="x", padx=PAD_SM, pady=2)
            self._step_labels.append(label)

        # Log area
        ctk.CTkLabel(
            self,
            text="Log Output",
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=PAD_XL, pady=(PAD_SM, 0))

        self._log_area = ctk.CTkTextbox(
            self,
            height=100,
            fg_color=BG_TERTIARY,
            text_color=TEXT_SECONDARY,
            font=FONT_MONO_SM,
            state="disabled",
        )
        self._log_area.pack(fill="both", expand=True, padx=PAD_XL, pady=(PAD_SM, PAD_LG))

    def update_step(
        self, index: int, success: bool, detail: str = ""
    ) -> None:
        """
        Update a specific step's status. Thread-safe (uses .after).

        Args:
            index: Step index (0-based).
            success: True for ✅, False for ❌.
            detail: Optional detail text to append.
        """
        try:
            self.after(0, lambda: self._apply_step_update(index, success, detail))
        except RuntimeError:
            # Fallback: direct update if .after() fails
            self._apply_step_update(index, success, detail)

    def update_step_direct(
        self, index: int, success: bool, detail: str = ""
    ) -> None:
        """
        Update a step directly (main thread only, no .after).

        Use this when calling from the main thread where
        .after() is not needed or may fail.
        """
        self._apply_step_update(index, success, detail)

    def _apply_step_update(
        self, index: int, success: bool, detail: str
    ) -> None:
        """Apply the actual step update to widgets."""
        if index < len(self._step_labels):
            icon = ICON_SUCCESS if success else ICON_FAIL
            color = ACCENT_GREEN if success else ACCENT_RED
            step_name = BOOTSTRAP_STEPS[index]
            text = f"{icon}  {step_name}"
            if detail:
                text += f"  —  {detail}"
            self._step_labels[index].configure(
                text=text, text_color=color,
            )
            # Mark next step as in-progress
            if success and index + 1 < len(self._step_labels):
                next_name = BOOTSTRAP_STEPS[index + 1]
                self._step_labels[index + 1].configure(
                    text=f"⏳  {next_name}...",
                    text_color=ACCENT_CYAN,
                )

    def add_log(self, message: str) -> None:
        """Append a message to the log area. Thread-safe."""
        try:
            self.after(0, lambda: self._apply_log(message))
        except RuntimeError:
            self._apply_log(message)

    def add_log_direct(self, message: str) -> None:
        """Append to log directly (main thread only)."""
        self._apply_log(message)

    def _apply_log(self, message: str) -> None:
        """Apply the actual log append to widgets."""
        self._log_area.configure(state="normal")
        self._log_area.insert("end", message + "\n")
        self._log_area.see("end")
        self._log_area.configure(state="disabled")

    def complete(self) -> None:
        """Mark setup as complete and auto-close after 3 seconds."""
        try:
            self.after(0, self._apply_complete)
        except RuntimeError:
            self._apply_complete()

    def _apply_complete(self) -> None:
        """Apply completion state."""
        self._apply_log("\n✅ Setup complete! LinkSync AI is ready.")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(3000, self.destroy)
