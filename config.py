"""
LinkSync AI — Central Configuration
====================================
All constants, paths, and defaults for the entire application.
No hardcoded values should exist anywhere else in the codebase.
Everything here is overridable via .env or agent_context.json.

See codex.md for a full explanation of each setting.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present (optional — all defaults work without it)
load_dotenv()

# ============================================================
# Paths
# ============================================================
PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
DB_PATH = DATA_DIR / "linksync.db"
CHROMA_PATH = DATA_DIR / "chroma"
CONTEXT_FILE = PROJECT_ROOT / "agent_context.json"
CONFIG_FILE = PROJECT_ROOT / "config.json"
ICON_PATH = ASSETS_DIR / "icon.png"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# ============================================================
# Hotkey (Win32 RegisterHotKey — no admin required)
# ============================================================
# Virtual key code for 'L' = 0x4C
import win32con

HOTKEY_ID = 1
HOTKEY_MODIFIERS = win32con.MOD_CONTROL | win32con.MOD_SHIFT
HOTKEY_VK = ord('L')  # Ctrl+Shift+L
HOTKEY_FALLBACK_VK = ord('K')  # Fallback: Ctrl+Shift+K
HOTKEY_DISPLAY = "Ctrl+Shift+L"

# ============================================================
# LLM Configuration (Local-First)
# ============================================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_TIMEOUT = 60  # seconds

# API Fallback (only used if Ollama is down AND key is configured)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

# ============================================================
# Content Processing
# ============================================================
CONTENT_LENGTH_THRESHOLD = 50_000  # chars — above this = "Title Only" mode
MAX_CRITIC_RETRIES = 2
NEGATIVE_SIMILARITY_THRESHOLD = 0.85  # cosine similarity for negative filter

# Adaptive summary length tiers (chars → max lines)
SUMMARY_LENGTH_TIERS = [
    (5_000, 3),      # Short article → 2-3 lines
    (20_000, 6),     # Medium blog/tutorial → 4-6 lines
    (50_000, 10),    # Deep technical content → 7-10 lines
]

# ============================================================
# Browser Detection
# ============================================================
CDP_PORT = int(os.getenv("CDP_PORT", "9222"))
CDP_URL = f"http://localhost:{CDP_PORT}/json"

# Registry of known browsers — extensible by adding entries
BROWSER_REGISTRY = {
    "chrome.exe": {
        "name": "Google Chrome",
        "chromium": True,
        "exe_search": "chrome.exe",
        "title_pattern": r".*Google Chrome$",
        "known_paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
    },
    "msedge.exe": {
        "name": "Microsoft Edge",
        "chromium": True,
        "exe_search": "msedge.exe",
        "title_pattern": r".*Edge$",
        "known_paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    "brave.exe": {
        "name": "Brave",
        "chromium": True,
        "exe_search": "brave.exe",
        "title_pattern": r".*Brave$",
        "known_paths": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
    },
    "opera.exe": {
        "name": "Opera",
        "chromium": True,
        "exe_search": "opera.exe",
        "title_pattern": r".*Opera$",
        "known_paths": [
            r"C:\Users\{user}\AppData\Local\Programs\Opera\opera.exe",
        ],
    },
    "vivaldi.exe": {
        "name": "Vivaldi",
        "chromium": True,
        "exe_search": "vivaldi.exe",
        "title_pattern": r".*Vivaldi$",
        "known_paths": [
            r"C:\Users\{user}\AppData\Local\Vivaldi\Application\vivaldi.exe",
        ],
    },
    "duckduckgo.exe": {
        "name": "DuckDuckGo",
        "chromium": True,
        "exe_search": "duckduckgo.exe",
        "title_pattern": r".*DuckDuckGo$",
        "known_paths": [],
    },
    "firefox.exe": {
        "name": "Firefox",
        "chromium": False,  # No CDP support — uses UIA fallback
        "exe_search": "firefox.exe",
        "title_pattern": r".*Mozilla Firefox$",
        "known_paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
    },
}

# ============================================================
# WhatsApp
# ============================================================
WHATSAPP_GROUP = os.getenv("WHATSAPP_GROUP", "ME")
WHATSAPP_KNOWN_PATHS = [
    r"C:\Users\{user}\AppData\Local\WhatsApp\WhatsApp.exe",
    r"C:\Program Files\WindowsApps",  # UWP apps directory
    r"C:\Program Files (x86)\WhatsApp",
]
WHATSAPP_STORE_ID = "9NKSQGP7F2NH"  # Microsoft Store Product ID
WHATSAPP_DOWNLOAD_URL = "https://www.whatsapp.com/download"

# ============================================================
# Privacy — Blacklisted Domains
# ============================================================
BLACKLISTED_DOMAINS = [
    # Banking & Finance
    "banking", "bank", "netbanking", "onlinebanking",
    "paypal.com", "stripe.com",
    # Email
    "mail.google.com", "outlook.live.com", "outlook.office.com",
    "mail.yahoo.com", "protonmail.com",
    # System / Settings
    "chrome://", "edge://", "about:", "localhost",
    "settings", "accounts.google.com",
    # Social Media Login/Settings
    "auth0.com", "login", "signin", "signup",
    # Health / Sensitive
    "health", "medical",
]

# ============================================================
# Message Formatting
# ============================================================
WHATSAPP_MESSAGE_TEMPLATE = """🔗 *LinkSync AI*
━━━━━━━━━━━━━━━━━━
📄 {summary}
🌐 {url}
━━━━━━━━━━━━━━━━━━"""

# ============================================================
# Scraper
# ============================================================
SCRAPER_TIMEOUT = 30_000  # milliseconds
SCRAPER_WAIT_UNTIL = "domcontentloaded"

# ============================================================
# Application Metadata
# ============================================================
APP_NAME = "LinkSync AI"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Autonomous browser-to-WhatsApp sync agent"
