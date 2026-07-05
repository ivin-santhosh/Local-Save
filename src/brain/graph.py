"""
LinkSync AI — LangGraph State Graph
=====================================
The central cognitive architecture. Wires all brain nodes
(Eye → Filter → Summarize → Critic) into a LangGraph
StateGraph with conditional edges for retries and aborts.

The graph processes each selected tab through the pipeline:
  1. Eye:    Blacklist + dedup + negative filter check
  2. Filter: Scrape page, determine summary strategy
  3. Summarize: Generate summary via LLM
  4. Critic: Validate quality (retry if needed)

Usage:
    from src.brain.graph import run_sync_pipeline
    results = run_sync_pipeline(tabs, progress_callback)
"""

import logging
from typing import Callable, Optional, TypedDict

from langgraph.graph import StateGraph, END, START

from src.brain.eye import eye_node
from src.brain.filter_node import filter_node
from src.brain.critic import critic_node
from src.brain.llm_provider import invoke_with_fallback, get_provider_name

logger = logging.getLogger(__name__)


# ============================================================
# State Definition
# ============================================================

class SyncState(TypedDict, total=False):
    """
    Shared state object that flows through the LangGraph pipeline.
    Each node reads from and writes to this state.
    """
    # Input
    url: str
    title: str

    # Eye node outputs
    abort: bool
    abort_reason: Optional[str]
    duplicate: bool
    negative_match: bool

    # Filter node outputs
    content: str
    title_only: bool
    page_title: str
    content_length: int
    summary_max_lines: int

    # Summarize node outputs
    summary: str

    # Critic node outputs
    approved: bool
    retry_count: int
    critique_reason: Optional[str]

    # Final
    dispatched: bool
    error: Optional[str]
    provider_used: str


# ============================================================
# Summarize Node
# ============================================================

def summarize_node(state: dict) -> dict:
    """
    Generate a professional summary of the page content using the LLM.

    Builds a prompt based on content type (full content vs title-only)
    and includes the adaptive line limit from the Filter node.

    Args:
        state: LangGraph state with content, page_title, summary_max_lines.

    Returns:
        Updated state with 'summary' and 'provider_used'.
    """
    url = state.get("url", "")
    page_title = state.get("page_title", "")
    content = state.get("content", "")
    title_only = state.get("title_only", False)
    max_lines = state.get("summary_max_lines", 5)
    critique = state.get("critique_reason")
    retry_count = state.get("retry_count", 0)

    logger.info(
        "Summarizing '%s' (max %d lines, attempt %d)...",
        page_title[:40], max_lines, retry_count + 1,
    )

    # ── Build the prompt ──
    if title_only:
        prompt = (
            f"The following web page is very long. Based ONLY on its title, "
            f"write a brief 1-2 line professional description.\n\n"
            f"Title: {page_title}\n"
            f"URL: {url}\n\n"
            f"Requirements:\n"
            f"- Maximum 2 lines\n"
            f"- Professional, third-person tone\n"
            f"- No first-person pronouns\n"
            f"- Just describe what the page is about"
        )
    else:
        # Truncate content to avoid token limits
        truncated = content[:15_000] if len(content) > 15_000 else content

        prompt = (
            f"Summarize the following web page content.\n\n"
            f"Title: {page_title}\n"
            f"URL: {url}\n\n"
            f"Content:\n{truncated}\n\n"
            f"Requirements:\n"
            f"- Maximum {max_lines} lines\n"
            f"- Professional, third-person tone\n"
            f"- No first-person pronouns (no 'I', 'we', 'my')\n"
            f"- Reference key topics from the page\n"
            f"- Be informative and concise"
        )

        # If this is a retry, include the critique feedback
        if critique and retry_count > 0:
            prompt += (
                f"\n\nPREVIOUS ATTEMPT WAS REJECTED:\n{critique}\n"
                f"Please fix these issues in your new summary."
            )

    # ── Invoke LLM ──
    try:
        summary = invoke_with_fallback(prompt)
        provider = get_provider_name()
        logger.info("Summary generated via %s (%d chars).", provider, len(summary))
        return {
            **state,
            "summary": summary,
            "provider_used": provider,
        }
    except Exception as exc:
        logger.error("Summarization failed: %s", exc)
        return {
            **state,
            "summary": f"[Summary unavailable: {page_title}]",
            "provider_used": "none",
            "error": str(exc),
        }


# ============================================================
# Conditional Edge Functions
# ============================================================

def _should_continue_after_eye(state: dict) -> str:
    """Route after Eye node: abort → END, else → filter."""
    if state.get("abort", False):
        return "end"
    return "filter"


def _should_continue_after_critic(state: dict) -> str:
    """Route after Critic: retry → summarize, else → END."""
    if not state.get("approved", False) and state.get("retry_count", 0) <= 2:
        return "summarize"
    return "end"


# ============================================================
# Graph Construction
# ============================================================

def _build_graph() -> StateGraph:
    """
    Build the LangGraph StateGraph with all nodes and edges.

    Flow:
        START → eye → (abort? → END | continue → filter)
        filter → summarize → critic → (retry? → summarize | END)

    Returns:
        A compiled StateGraph ready to invoke.
    """
    graph = StateGraph(dict)

    # Add nodes
    graph.add_node("eye", eye_node)
    graph.add_node("filter", filter_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("critic", critic_node)

    # Wire edges
    graph.add_edge(START, "eye")

    graph.add_conditional_edges(
        "eye",
        _should_continue_after_eye,
        {"filter": "filter", "end": END},
    )

    graph.add_edge("filter", "summarize")
    graph.add_edge("summarize", "critic")

    graph.add_conditional_edges(
        "critic",
        _should_continue_after_critic,
        {"summarize": "summarize", "end": END},
    )

    return graph


# Compile the graph once at module level
_compiled_graph = _build_graph().compile()


# ============================================================
# Public API
# ============================================================

import threading
db_lock = threading.Lock()


def run_sync_pipeline(
    tabs: list[dict],
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> list[dict]:
    """
    Process a list of tabs through the full sync pipeline concurrently.

    Each tab is submitted to a ThreadPoolExecutor and goes through:
    Eye → Filter → Summarize → Critic.
    Progress is reported after each tab completes.

    Args:
        tabs: List of tab dicts with 'title', 'url', 'domain' keys.
        progress_callback: Optional callable(tab_index, status_icon, status_text)
            for UI updates.

    Returns:
        List of result dicts, one per tab, with all state fields
        plus a 'status' field ('summarized', 'skipped', 'error').
    """
    from concurrent.futures import ThreadPoolExecutor

    results = [None] * len(tabs)
    max_workers = min(5, len(tabs)) if tabs else 1

    logger.info("Starting concurrent sync pipeline with %d worker agents...", max_workers)

    def worker_task(i: int, tab: dict) -> dict:
        url = tab.get("url", "")
        title = tab.get("title", "")

        logger.info("Processing tab %d/%d: %s", i + 1, len(tabs), title[:40])

        if progress_callback:
            progress_callback(i, "⏳", "Processing...")

        # Prepare initial state
        initial_state: dict = {
            "url": url,
            "title": title,
            "domain": tab.get("domain", ""),
            "browser": tab.get("browser", ""),
            "abort": False,
            "abort_reason": None,
            "duplicate": False,
            "negative_match": False,
            "content": "",
            "title_only": False,
            "page_title": title,
            "content_length": 0,
            "summary_max_lines": 5,
            "summary": "",
            "approved": False,
            "retry_count": 0,
            "critique_reason": None,
            "dispatched": False,
            "error": None,
            "provider_used": "none",
        }

        try:
            final_state = _compiled_graph.invoke(
                initial_state,
                config={"recursion_limit": 10},
            )

            # Determine result status
            if final_state.get("abort"):
                status = "skipped"
                status_icon = "⏭️"
                status_text = final_state.get("abort_reason", "Skipped")
            elif final_state.get("summary") and final_state["summary"].strip():
                status = "summarized"
                status_icon = "✅"
                status_text = "Summarized"

                # Store in vector memory (thread-safe write using db_lock)
                try:
                    from src.storage.vector_store import add_article
                    with db_lock:
                        add_article(
                            url=url,
                            summary=final_state.get("summary", ""),
                            metadata={
                                "title": title,
                                "provider": final_state.get("provider_used", ""),
                            },
                        )
                except Exception as exc:
                    logger.warning("Failed to store in vector memory: %s", exc)

            elif final_state.get("error"):
                status = "error"
                status_icon = "❌"
                status_text = final_state.get("error", "Unknown error")
            else:
                status = "error"
                status_icon = "❌"
                status_text = "No summary generated"

            final_state["status"] = status

        except Exception as exc:
            logger.error("Pipeline error for tab %d: %s", i, exc)
            final_state = {
                **initial_state,
                "error": str(exc),
                "status": "error",
            }
            status_icon = "❌"
            status_text = str(exc)

        if progress_callback:
            progress_callback(i, status_icon, status_text)

        return final_state

    # Submit tasks concurrently to the thread pool (lightweight agents)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(worker_task, i, tab): i
            for i, tab in enumerate(tabs)
        }
        for future in future_to_idx:
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error("Tab worker thread %d failed with exception: %s", idx, exc)
                results[idx] = {
                    "url": tabs[idx].get("url", ""),
                    "title": tabs[idx].get("title", ""),
                    "status": "error",
                    "error": str(exc),
                }

    logger.info(
        "Pipeline complete: %d tabs processed, %d summarized.",
        len(results),
        sum(1 for r in results if r.get("status") == "summarized"),
    )

    return results
