"""
LinkSync AI — Dual LLM Provider
=================================
Manages the local-first LLM strategy:

  Primary:  Ollama (local, private, fast, no cost)
  Fallback: OpenAI / Groq API (only if local is down AND key configured)

Every provider switch sends a Windows toast notification so
the user always knows which engine processed their data.

Usage:
    from src.brain.llm_provider import invoke_with_fallback, get_provider_name
    summary = invoke_with_fallback("Summarize this article...")
"""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
)

logger = logging.getLogger(__name__)

# Module-level state — tracks which provider is currently active
_current_provider: str = "none"
_llm_instance: Optional[BaseChatModel] = None


def check_ollama_health() -> bool:
    """
    Check if Ollama is running and responsive.

    Delegates to ollama_manager for the actual health check,
    keeping this module decoupled from process management.

    Returns:
        True if Ollama is reachable, False otherwise.
    """
    from src.brain.ollama_manager import is_running
    return is_running()


def _notify_provider_switch(from_provider: str, to_provider: str) -> None:
    """
    Send a Windows toast notification about a provider change.

    Args:
        from_provider: The provider that failed (e.g., 'ollama').
        to_provider: The provider being switched to (e.g., 'openai').
    """
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(
            "LinkSync AI — Provider Switch",
            f"⚠️ {from_provider} unavailable. Switched to {to_provider}.",
            duration=5,
            threaded=True,
        )
    except Exception:
        # Toast is nice-to-have, not critical
        logger.debug("Could not show toast notification for provider switch.")


def get_llm() -> BaseChatModel:
    """
    Get the best available LLM instance.

    Priority:
    1. Ollama (local) — always preferred
    2. OpenAI API — if OPENAI_API_KEY is configured
    3. Groq API — if GROQ_API_KEY is configured

    Returns:
        A LangChain chat model instance.

    Raises:
        RuntimeError: If no LLM provider is available.
    """
    global _current_provider, _llm_instance

    # Try Ollama first (local)
    if check_ollama_health():
        if _current_provider != "ollama":
            if _current_provider not in ("none", "ollama"):
                _notify_provider_switch(_current_provider, "Ollama (local)")
            _current_provider = "ollama"
            logger.info("Using Ollama (%s) — local, private.", OLLAMA_MODEL)

        from langchain_ollama import ChatOllama
        _llm_instance = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            timeout=OLLAMA_TIMEOUT,
            temperature=0.3,
        )
        return _llm_instance

    # Try OpenAI fallback
    if OPENAI_API_KEY:
        if _current_provider != "openai":
            _notify_provider_switch(
                _current_provider or "Ollama", "OpenAI API"
            )
            _current_provider = "openai"
            logger.info("Ollama unavailable. Using OpenAI (%s).", OPENAI_MODEL)

        from langchain_openai import ChatOpenAI
        _llm_instance = ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            temperature=0.3,
        )
        return _llm_instance

    # Try Groq fallback
    if GROQ_API_KEY:
        if _current_provider != "groq":
            _notify_provider_switch(
                _current_provider or "Ollama", "Groq API"
            )
            _current_provider = "groq"
            logger.info("Ollama unavailable. Using Groq (%s).", GROQ_MODEL)

        from langchain_openai import ChatOpenAI
        _llm_instance = ChatOpenAI(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            temperature=0.3,
        )
        return _llm_instance

    raise RuntimeError(
        "No LLM provider available. Start Ollama or configure an API key in .env"
    )


def invoke_with_fallback(prompt: str) -> str:
    """
    Invoke the LLM with automatic provider fallback.

    Tries the current best provider. If it fails mid-request,
    switches to the next available provider and retries.

    Args:
        prompt: The prompt text to send to the LLM.

    Returns:
        The LLM's response text.

    Raises:
        RuntimeError: If all providers fail.
    """
    global _current_provider

    # First attempt
    try:
        llm = get_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except RuntimeError:
        raise
    except Exception as first_error:
        logger.warning(
            "LLM invocation failed with %s: %s",
            _current_provider, first_error,
        )

        # Force a re-evaluation of providers
        old_provider = _current_provider
        _current_provider = "none"

        try:
            llm = get_llm()
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as second_error:
            logger.error(
                "All LLM providers failed. First: %s, Second: %s",
                first_error, second_error,
            )
            raise RuntimeError(
                f"All LLM providers failed. "
                f"{old_provider}: {first_error}"
            ) from second_error


def get_provider_name() -> str:
    """Return the name of the currently active LLM provider."""
    return _current_provider
