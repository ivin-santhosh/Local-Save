# LinkSync AI — CODEX (Living Documentation)
> Last updated: 2026-05-27 | v1.0.1 | 40 files

This is the **living documentation** for the LinkSync AI codebase.
Every file is catalogued with its purpose, key functions, and dependencies.
Updated with every meaningful change.

---

## Architecture Overview

```
User presses Ctrl+Shift+L
        │
        ▼
┌─ Hotkey Listener (Win32 RegisterHotKey) ─────────────────────┐
│   global_hotkey.py                                            │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌─ Tab Capture ────────────────────────────────────────────────┐
│   tab_capture.py → CDP (Chromium) or UIA (Firefox/other)     │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌─ Tab Selector UI ────────────────────────────────────────────┐
│   tab_selector.py → Dark CustomTkinter popup with checkboxes │
└──────────────────────────────┬────────────────────────────────┘
                               │ User selects → PROCEED
                               ▼
┌─ LangGraph Pipeline ─────────────────────────────────────────┐
│   ┌─────────┐   ┌──────────┐   ┌───────────┐   ┌─────────┐ │
│   │   Eye   │──▶│  Filter  │──▶│ Summarize │──▶│ Critic  │ │
│   │blacklist│   │ scrape & │   │ LLM call  │   │ quality │ │
│   │ + dedup │   │ length   │   │ (local)   │   │  gate   │ │
│   └────┬────┘   └──────────┘   └───────────┘   └────┬────┘ │
│        │ abort?                        retry? ◀──────┘      │
└────────┴───────────────────────────────┬─────────────────────┘
                                         │
                                         ▼
┌─ Dispatch Orchestrator ──────────────────────────────────────┐
│   dispatcher.py → WhatsApp Desktop → Web fallback → Queue   │
└──────────────────────────────────────────────────────────────┘
```

---

## File Catalogue

### Root Files

| File | Size | Purpose |
|------|------|---------|
| `main.py` | 8.3 KB | Application entry point. Orchestrates bootstrap, storage init, hotkey, tray, and sync cycle |
| `config.py` | 7.0 KB | Central configuration. ALL constants, paths, browser registry, blacklisted domains |
| `requirements.txt` | 961 B | Python dependencies grouped by function |
| `LinkSync_AI.bat` | 1.7 KB | One-click launcher. Creates venv + installs deps on first run |
| `.env.example` | 861 B | Template for optional API keys (local-first — no keys needed) |
| `.gitignore` | 354 B | Git exclusions for venv, data, secrets, IDE files |

---

### src/storage/ — Persistent Memory

| File | Size | Purpose |
|------|------|---------|
| `context_manager.py` | 8.6 KB | JSON-based agent memory (`agent_context.json`). Persists discovered paths, preferences, learning. Thread-safe with atomic writes |
| `database.py` | 10.5 KB | SQLite layer. `sync_logs` table for history, dispatch patterns. WAL mode, thread-safe |
| `vector_store.py` | 9.6 KB | ChromaDB semantic memory. `article_embeddings` + `negative_filter` collections. Uses all-MiniLM-L6-v2 embeddings |
| `__init__.py` | 1.8 KB | Re-exports all public APIs from all 3 modules |

---

### src/hotkey/ — Global Keyboard Shortcut

| File | Size | Purpose |
|------|------|---------|
| `global_hotkey.py` | 5.9 KB | Win32 RegisterHotKey (no admin). Ctrl+Shift+L primary, Ctrl+Shift+K fallback. Daemon thread |

---

### src/capture/ — Browser Tab Detection

| File | Size | Purpose |
|------|------|---------|
| `tab_capture.py` | 9.9 KB | Auto-detects foreground browser. CDP for Chromium (all tabs), UIA for Firefox (active tab). Extensible via BROWSER_REGISTRY |

---

### src/brain/ — Cognitive Architecture (LangGraph)

| File | Size | Purpose |
|------|------|---------|
| `graph.py` | 10.4 KB | LangGraph StateGraph wiring: Eye→Filter→Summarize→Critic. Conditional edges for abort/retry. `run_sync_pipeline()` |
| `ollama_manager.py` | 7.5 KB | **On-demand Ollama lifecycle**: starts Ollama only during sync, stops after. Reference-counted, context manager, won't touch externally-started instances. Loosely coupled — reusable by any agent |
| `llm_provider.py` | 5.7 KB | Dual LLM: Ollama local-first → OpenAI/Groq API fallback. Delegates health checks to ollama_manager. Toast notification on every switch |
| `eye.py` | 4.2 KB | Node A — Blacklist check, dedup check (SQLite 24h), negative filter (ChromaDB) |
| `filter_node.py` | 3.7 KB | Node B — Playwright scrape, adaptive summary length (3/6/10 lines by content size) |
| `critic.py` | 5.2 KB | Node C — Quality gate: length, tone (no 1st person), relevance, format. Up to 2 retries |

---

### src/scraper/ — Page Content Extraction

| File | Size | Purpose |
|------|------|---------|
| `page_scraper.py` | 6.0 KB | Headless Playwright Chromium. Singleton browser, sync wrappers around async API |

---

### src/discovery/ — Intelligent App Finder

| File | Size | Purpose |
|------|------|---------|
| `app_finder.py` | 11.2 KB | 6-step hierarchy: cached context → known paths → registry → C: scan → D: scan → install. Threaded with timeout |

---

### src/dispatch/ — WhatsApp Message Delivery

| File | Size | Purpose |
|------|------|---------|
| `dispatcher.py` | 6.1 KB | Orchestrator: Desktop → Web → queue. Formats messages, handles batch dispatch |
| `whatsapp_desktop.py` | 8.4 KB | pywinauto UIA automation. Self-healing element discovery (multiple title patterns) |
| `whatsapp_web.py` | 6.1 KB | Playwright WhatsApp Web. Persistent context for session reuse (scan QR once) |

---

### src/ui/ — CustomTkinter Windows

| File | Size | Purpose |
|------|------|---------|
| `theme.py` | 3.5 KB | Cybersecurity dark theme: colors, fonts, spacing, sizes. All UI constants |
| `tab_selector.py` | 16.2 KB | Hero popup: checkbox per tab → progress view → final report. Blacklist greying |
| `logs_window.py` | 7.3 KB | Recent sync logs: timestamp, domain, summary, status badge, Mark Irrelevant button |
| `settings_dialog.py` | 6.9 KB | Config form: WhatsApp group, Ollama model, API key, blacklist editor |
| `progress_window.py` | 5.6 KB | First-run bootstrap: step checklist with live status + log area |

---

### src/tray/ — System Tray

| File | Size | Purpose |
|------|------|---------|
| `system_tray.py` | 3.7 KB | pystray icon. Menu: Sync Now (default), Logs, Settings, Exit. Double-click = sync |

---

### src/bootstrap/ — First-Run Setup

| File | Size | Purpose |
|------|------|---------|
| `first_run.py` | 7.1 KB | 8-step setup: Python check, deps, Playwright, browsers, WhatsApp, Ollama, context, shortcut |

---

### assets/

| File | Purpose |
|------|---------|
| `icon.png` | System tray icon (electric cyan chain-link on dark navy) |

---

## Key Design Decisions

1. **No hardcoded values** — Everything flows from `config.py` → consumed by modules
2. **No admin required** — Uses `RegisterHotKey` instead of `keyboard` library
3. **Local-first** — Ollama is always preferred. API keys are optional fallback only
4. **On-demand Ollama** — Ollama starts only during sync cycles and stops after. Zero RAM usage while idle. If another agent already has Ollama running, we don't interfere
5. **Loosely coupled Ollama** — `ollama_manager.py` is fully reusable by other AI agents (context manager, reference counting, force shutdown)
6. **Self-healing** — WhatsApp automation tries multiple element patterns, caches what works
7. **Modular** — Every module is independent. Replace any single module without affecting others
8. **Privacy** — Blacklisted domains are checked FIRST, before any scraping or API calls
9. **Transparency** — Provider switches trigger toast notifications. All actions logged

## Total Codebase Size

- **40 files** across 10 modules
- **~190 KB** of Python source code
- **0 hardcoded paths** in non-config files
