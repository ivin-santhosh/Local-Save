"""
LinkSync AI — Ollama Lifecycle Manager
========================================
Manages the Ollama process lifecycle so it only runs when
actually needed (during a sync cycle), not 24/7.

Key design decisions:
  - If Ollama was ALREADY running (e.g., another AI agent started it),
    we DON'T stop it — we only stop what we started.
  - Fully decoupled from LinkSync AI — any other agent can import
    and use this module independently.
  - Thread-safe: multiple callers can safely call start/stop.

Usage:
    from src.brain.ollama_manager import ensure_running, shutdown

    ensure_running()          # Start if not already running
    # ... do LLM work ...
    shutdown()                # Stop only if we started it

    # Or use the context manager:
    with ollama_session():
        invoke_with_fallback("Summarize this...")
"""

import atexit
import logging
import subprocess
import time
import threading
from contextlib import contextmanager
from typing import Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_EXE_PATH

logger = logging.getLogger(__name__)

# ============================================================
# Module State
# ============================================================

_lock = threading.Lock()
_process: Optional[subprocess.Popen] = None
_we_started_it: bool = False
_active_sessions: int = 0  # Reference counter for nested usage


def _get_ollama_cmd() -> str:
    """
    Resolve the Ollama executable path.

    Checks (in order):
    1. Config OLLAMA_EXE_PATH (from .env or auto-discovered)
    2. agent_context.json (cached from previous discovery)
    3. Falls back to bare 'ollama' (relies on PATH)
    """
    import os

    # 1. Config path
    if OLLAMA_EXE_PATH and os.path.isfile(OLLAMA_EXE_PATH):
        return OLLAMA_EXE_PATH

    # 2. Cached in agent_context.json
    try:
        from src.storage.context_manager import get_value
        cached = get_value("discovered_apps.ollama.path")
        if cached and os.path.isfile(cached):
            return cached
    except Exception:
        pass

    # 3. Bare command (hope it's on PATH)
    return "ollama"


def is_running() -> bool:
    """
    Check if Ollama is currently running and responsive.

    Returns:
        True if Ollama responds to a health check at OLLAMA_BASE_URL.
    """
    try:
        resp = requests.get(OLLAMA_BASE_URL, timeout=3)
        return resp.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False
    except Exception as exc:
        logger.debug("Ollama health check error: %s", exc)
        return False


def ensure_running(timeout: int = 30) -> bool:
    """
    Ensure Ollama is running. Starts it if needed.

    If Ollama is already running (started by another process or
    AI agent), this is a no-op — we won't touch it.

    Args:
        timeout: Max seconds to wait for Ollama to become ready.

    Returns:
        True if Ollama is running after this call, False if we
        failed to start it.
    """
    global _process, _we_started_it, _active_sessions

    with _lock:
        _active_sessions += 1

        # Already running? Great — don't touch it
        if is_running():
            if not _we_started_it:
                logger.info(
                    "Ollama already running (external process). "
                    "Will NOT stop it on shutdown."
                )
            return True

        # Try to start it
        logger.info("Starting Ollama for this sync cycle...")
        ollama_cmd = _get_ollama_cmd()
        try:
            _process = subprocess.Popen(
                [ollama_cmd, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,  # No console window
            )
            _we_started_it = True

            # Register cleanup in case of unclean exit
            atexit.register(shutdown)

        except FileNotFoundError:
            logger.error(
                "Ollama not found on PATH. Install from https://ollama.com"
            )
            _active_sessions -= 1
            return False
        except Exception as exc:
            logger.error("Failed to start Ollama: %s", exc)
            _active_sessions -= 1
            return False

    # Wait for Ollama to become ready (outside the lock)
    return _wait_for_ready(timeout)


def _wait_for_ready(timeout: int) -> bool:
    """
    Wait for Ollama to respond to health checks.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if Ollama became ready within the timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        if is_running():
            elapsed = time.time() - start
            logger.info("Ollama ready in %.1fs.", elapsed)
            return True
        time.sleep(0.5)

    logger.error("Ollama did not become ready within %ds.", timeout)
    return False


def shutdown() -> None:
    """
    Stop Ollama — but ONLY if we started it.

    If Ollama was already running before we called ensure_running(),
    this is a no-op. This ensures other AI agents or user processes
    aren't disrupted.

    Safe to call multiple times.
    """
    global _process, _we_started_it, _active_sessions

    with _lock:
        _active_sessions = max(0, _active_sessions - 1)

        # Don't stop if other sessions are still using it
        if _active_sessions > 0:
            logger.debug(
                "Ollama shutdown deferred: %d active sessions remaining.",
                _active_sessions,
            )
            return

        # Only stop if WE started it
        if not _we_started_it:
            logger.debug("Ollama was external — leaving it running.")
            return

        if _process is None:
            return

        logger.info("Stopping Ollama (we started it, sync cycle complete).")
        try:
            _process.terminate()
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Ollama didn't stop gracefully. Killing...")
            _process.kill()
        except Exception as exc:
            logger.debug("Ollama shutdown error: %s", exc)
        finally:
            _process = None
            _we_started_it = False


def force_shutdown() -> None:
    """
    Force-stop Ollama regardless of who started it or active sessions.

    Use only during application exit.
    """
    global _process, _we_started_it, _active_sessions

    with _lock:
        _active_sessions = 0

        if not _we_started_it or _process is None:
            return

        logger.info("Force-stopping Ollama (app exit).")
        try:
            _process.terminate()
            _process.wait(timeout=5)
        except Exception:
            try:
                _process.kill()
            except Exception:
                pass
        finally:
            _process = None
            _we_started_it = False


@contextmanager
def ollama_session(timeout: int = 30):
    """
    Context manager for Ollama lifecycle.

    Starts Ollama if needed, yields, then stops it if we started it.
    Supports nesting — Ollama only stops when the last session exits.

    Usage:
        with ollama_session():
            result = invoke_with_fallback("Summarize this...")

    Args:
        timeout: Max seconds to wait for Ollama startup.

    Yields:
        True if Ollama is running, False if startup failed.
    """
    ready = ensure_running(timeout=timeout)
    try:
        yield ready
    finally:
        shutdown()


def was_started_by_us() -> bool:
    """Check if we started the current Ollama process."""
    return _we_started_it


def get_status() -> dict:
    """
    Get the current Ollama status for diagnostics.

    Returns:
        Dict with: running, started_by_us, active_sessions, pid.
    """
    return {
        "running": is_running(),
        "started_by_us": _we_started_it,
        "active_sessions": _active_sessions,
        "pid": _process.pid if _process else None,
    }
