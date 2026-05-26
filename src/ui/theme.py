"""
LinkSync AI — Cybersecurity Dark Theme
=======================================
All visual constants for the application UI.
Used by every CustomTkinter window for a consistent,
modern, cybersecurity-inspired aesthetic.

Color philosophy:
  - Deep navy backgrounds for a premium, serious feel
  - Electric cyan as the primary accent (trust, technology)
  - Neon green for success states (hacker/cybersec aesthetic)
  - Coral red for errors/alerts
  - All colors chosen for high contrast and readability
"""

# ============================================================
# Color Palette
# ============================================================

# Backgrounds
BG_PRIMARY = "#0a0e1a"       # Deep navy — main window background
BG_SECONDARY = "#111827"     # Slightly lighter — card/panel background
BG_TERTIARY = "#1a2332"      # Input fields, list items
BG_HOVER = "#1e293b"         # Hover state for interactive elements

# Accents
ACCENT_CYAN = "#00f0ff"      # Electric cyan — primary accent, headings
ACCENT_GREEN = "#39ff14"     # Neon green — success, active states
ACCENT_RED = "#ff3366"       # Coral red — errors, alerts, critical
ACCENT_YELLOW = "#fbbf24"    # Amber — warnings
ACCENT_PURPLE = "#a855f7"    # Purple — secondary highlights

# Text
TEXT_PRIMARY = "#e0e6ed"     # Light grey — main readable text
TEXT_SECONDARY = "#94a3b8"   # Muted grey — descriptions, timestamps
TEXT_MUTED = "#6b7280"       # Very muted — disabled, placeholder
TEXT_INVERSE = "#0a0e1a"     # Dark — text on light/accent backgrounds

# Borders & Glow
BORDER_DEFAULT = "#1e293b"   # Subtle border
BORDER_ACCENT = "#00f0ff33"  # Translucent cyan glow
BORDER_FOCUS = "#00f0ff"     # Solid cyan — focused element
BORDER_RADIUS = 12           # Default corner radius

# ============================================================
# Typography
# ============================================================

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Cascadia Mono"

FONT_HEADING_LG = (FONT_FAMILY, 20, "bold")
FONT_HEADING = (FONT_FAMILY, 16, "bold")
FONT_HEADING_SM = (FONT_FAMILY, 14, "bold")
FONT_BODY = (FONT_FAMILY, 12)
FONT_BODY_SM = (FONT_FAMILY, 11)
FONT_CAPTION = (FONT_FAMILY, 10)
FONT_MONO_MD = (FONT_MONO, 12)
FONT_MONO_SM = (FONT_MONO, 10)

# ============================================================
# Spacing
# ============================================================

PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 24
PAD_XXL = 32

# ============================================================
# Component Sizes
# ============================================================

BUTTON_HEIGHT = 36
BUTTON_WIDTH = 140
INPUT_HEIGHT = 36
CHECKBOX_SIZE = 20
PROGRESS_HEIGHT = 8
SCROLLBAR_WIDTH = 10

# ============================================================
# Window Defaults
# ============================================================

WINDOW_MIN_WIDTH = 480
WINDOW_MIN_HEIGHT = 400
SELECTOR_WIDTH = 560
SELECTOR_HEIGHT = 520
LOGS_WIDTH = 720
LOGS_HEIGHT = 500
SETTINGS_WIDTH = 480
SETTINGS_HEIGHT = 520
PROGRESS_WIDTH = 500
PROGRESS_HEIGHT = 380

# ============================================================
# Status Icons (Unicode)
# ============================================================

ICON_SUCCESS = "✅"
ICON_FAIL = "❌"
ICON_PENDING = "⏳"
ICON_PROCESSING = "🧠"
ICON_SKIP = "⏭️"
ICON_LOCK = "🔒"
ICON_LINK = "🔗"
ICON_WARNING = "⚠️"
ICON_CHECK = "☑"
ICON_UNCHECK = "☐"
