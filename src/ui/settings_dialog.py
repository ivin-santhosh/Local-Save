"""
LinkSync AI — Settings Dialog
================================
Configuration dialog for user preferences:
- WhatsApp group name
- Ollama model selection
- API key (optional fallback)
- Blacklisted domains editor

All settings are persisted to agent_context.json.
"""

import logging
from typing import Optional

import customtkinter as ctk

from src.ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_HOVER,
    ACCENT_CYAN, ACCENT_GREEN,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    FONT_HEADING, FONT_BODY, FONT_BODY_SM, FONT_CAPTION,
    PAD_SM, PAD_MD, PAD_LG, PAD_XL,
    SETTINGS_WIDTH, SETTINGS_HEIGHT,
)
from config import APP_NAME, WHATSAPP_GROUP, OLLAMA_MODEL

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")


class SettingsDialog(ctk.CTkToplevel):
    """
    Settings dialog for configuring LinkSync AI preferences.

    All changes are saved to agent_context.json for persistence
    across sessions.
    """

    def __init__(self, master: Optional[ctk.CTk] = None):
        super().__init__(master)

        self.title(f"⚙️ {APP_NAME} — Settings")
        self.geometry(f"{SETTINGS_WIDTH}x{SETTINGS_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG_PRIMARY)
        self.attributes("-topmost", True)

        # Center
        self.update_idletasks()
        x = (self.winfo_screenwidth() - SETTINGS_WIDTH) // 2
        y = (self.winfo_screenheight() - SETTINGS_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        """Build the settings form."""
        # Header
        header = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="⚙️  Settings",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        ).pack(padx=PAD_XL, pady=PAD_LG)

        # Form
        form = ctk.CTkScrollableFrame(self, fg_color=BG_PRIMARY)
        form.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_SM)

        # WhatsApp Group
        self._wa_group = self._add_field(
            form, "WhatsApp Group Name",
            "The WhatsApp group to send summaries to",
        )

        # Ollama Model
        self._ollama_model = self._add_field(
            form, "Ollama Model",
            "Local LLM model name (e.g., llama3, mistral, gemma2)",
        )

        # API Key
        self._api_key = self._add_field(
            form, "OpenAI API Key (Optional)",
            "Only used as fallback when Ollama is unavailable",
            show="*",
        )

        # Blacklisted Domains
        ctk.CTkLabel(
            form,
            text="Blacklisted Domains",
            font=FONT_BODY,
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=PAD_SM, pady=(PAD_LG, 0))

        ctk.CTkLabel(
            form,
            text="One domain per line — these URLs will be auto-skipped",
            font=FONT_CAPTION,
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=PAD_SM, pady=(0, PAD_SM))

        self._blacklist_text = ctk.CTkTextbox(
            form,
            height=120,
            fg_color=BG_TERTIARY,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY_SM,
            border_color=ACCENT_CYAN,
            border_width=1,
        )
        self._blacklist_text.pack(fill="x", padx=PAD_SM, pady=PAD_SM)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0)
        btn_frame.pack(fill="x", side="bottom")

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color="transparent",
            border_width=1,
            border_color=TEXT_MUTED,
            text_color=TEXT_MUTED,
            hover_color=BG_HOVER,
            font=FONT_BODY_SM,
            command=self.destroy,
        ).pack(side="left", padx=PAD_LG, pady=PAD_MD)

        ctk.CTkButton(
            btn_frame,
            text="💾  Save",
            width=120,
            fg_color=ACCENT_CYAN,
            text_color=BG_PRIMARY,
            hover_color=ACCENT_GREEN,
            font=FONT_BODY,
            command=self._save_settings,
        ).pack(side="right", padx=PAD_LG, pady=PAD_MD)

    def _add_field(
        self, parent, label: str, hint: str, show: str = ""
    ) -> ctk.CTkEntry:
        """Add a labeled input field to the form."""
        ctk.CTkLabel(
            parent, text=label,
            font=FONT_BODY, text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=PAD_SM, pady=(PAD_LG, 0))

        ctk.CTkLabel(
            parent, text=hint,
            font=FONT_CAPTION, text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=PAD_SM, pady=(0, PAD_SM))

        entry = ctk.CTkEntry(
            parent,
            fg_color=BG_TERTIARY,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY_SM,
            border_color=ACCENT_CYAN,
            border_width=1,
            show=show,
        )
        entry.pack(fill="x", padx=PAD_SM, pady=PAD_SM)
        return entry

    def _load_settings(self) -> None:
        """Load current settings from context."""
        try:
            from src.storage.context_manager import get_value

            wa_group = get_value("user_preferences.whatsapp_group") or WHATSAPP_GROUP
            model = get_value("user_preferences.ollama_model") or OLLAMA_MODEL
            api_key = get_value("user_preferences.api_key") or ""
            blacklist = get_value("user_preferences.blacklisted_domains") or []

            self._wa_group.insert(0, wa_group)
            self._ollama_model.insert(0, model)
            self._api_key.insert(0, api_key)
            self._blacklist_text.insert("1.0", "\n".join(blacklist))
        except Exception as exc:
            logger.warning("Failed to load settings: %s", exc)
            self._wa_group.insert(0, WHATSAPP_GROUP)
            self._ollama_model.insert(0, OLLAMA_MODEL)

    def _save_settings(self) -> None:
        """Save settings to agent_context.json."""
        try:
            from src.storage.context_manager import set_value

            set_value("user_preferences.whatsapp_group", self._wa_group.get())
            set_value("user_preferences.ollama_model", self._ollama_model.get())

            api_key = self._api_key.get()
            if api_key:
                set_value("user_preferences.api_key", api_key)

            blacklist_text = self._blacklist_text.get("1.0", "end-1c")
            domains = [d.strip() for d in blacklist_text.split("\n") if d.strip()]
            set_value("user_preferences.blacklisted_domains", domains)

            logger.info("Settings saved.")
            self.destroy()
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)
