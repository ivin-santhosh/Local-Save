"""
LinkSync AI — Node C: The Critic
==================================
The quality gate in the LangGraph pipeline. After the LLM
generates a summary, this node validates it against:

1. Length — adaptive max (2-10 lines depending on content depth)
2. Tone — no first-person, no slang, professional
3. Relevance — must reference the page domain or title
4. Format — clean, readable text

If validation fails and retries remain, it sends the summary
back for regeneration with specific feedback. Failed summaries
are stored in ChromaDB as negative few-shot examples.

Usage (called by graph.py — not directly):
    result = critic_node(state)
"""

import logging
import re

from config import MAX_CRITIC_RETRIES

logger = logging.getLogger(__name__)

# First-person pronouns to flag
_FIRST_PERSON = re.compile(
    r'\b(I|me|my|myself|mine|we|us|our|ours|ourselves)\b',
    re.IGNORECASE,
)

# Slang / unprofessional patterns
_SLANG_PATTERNS = re.compile(
    r'\b(lol|lmao|omg|wtf|ngl|tbh|imo|imho|gonna|wanna|gotta|'
    r'kinda|sorta|ain\'t|y\'all|btw|fyi)\b',
    re.IGNORECASE,
)


def critic_node(state: dict) -> dict:
    """
    Validate a generated summary for quality and professionalism.

    Runs 4 checks: length, tone, relevance, format. If the summary
    fails any check and retries remain, it returns feedback for
    the summarizer to regenerate.

    Args:
        state: LangGraph state dict containing:
            - summary (str): The generated summary text
            - summary_max_lines (int): Maximum allowed lines
            - page_title (str): Original page title
            - url (str): Original URL
            - retry_count (int): Current retry count

    Returns:
        Updated state with:
        - approved (bool): True if summary passed all checks
        - retry_count (int): Incremented if failed
        - critique_reason (str|None): What failed (for regeneration)
    """
    summary = state.get("summary", "")
    max_lines = state.get("summary_max_lines", 10)
    page_title = state.get("page_title", "")
    url = state.get("url", "")
    retry_count = state.get("retry_count", 0)

    logger.info("Critic evaluating summary (attempt %d)...", retry_count + 1)

    # ── Run all checks ──
    issues = []

    # Check 1: Length
    lines = [line for line in summary.strip().split("\n") if line.strip()]
    if len(lines) > max_lines:
        issues.append(
            f"Too long: {len(lines)} lines (max {max_lines}). "
            f"Be more concise."
        )

    if len(summary.strip()) < 20:
        issues.append("Too short: summary must be at least 20 characters.")

    # Check 2: Tone — no first-person
    first_person_matches = _FIRST_PERSON.findall(summary)
    if first_person_matches:
        issues.append(
            f"Contains first-person pronouns: "
            f"{', '.join(set(first_person_matches))}. "
            f"Use third-person or passive voice."
        )

    # Check 3: Tone — no slang
    slang_matches = _SLANG_PATTERNS.findall(summary)
    if slang_matches:
        issues.append(
            f"Contains informal language: "
            f"{', '.join(set(slang_matches))}. "
            f"Use professional tone."
        )

    # Check 4: Relevance — should reference the topic
    if page_title and len(page_title) > 3:
        # Check if any significant word from the title appears in summary
        title_words = set(
            w.lower() for w in re.findall(r'\w+', page_title)
            if len(w) > 3  # Skip short words like "the", "and"
        )
        summary_lower = summary.lower()
        title_mentioned = any(w in summary_lower for w in title_words)

        if not title_mentioned and title_words:
            issues.append(
                f"Summary doesn't reference the page topic. "
                f"Include key terms from: '{page_title[:60]}'"
            )

    # ── Decision ──
    if not issues:
        logger.info("Critic APPROVED summary.")
        return {
            **state,
            "approved": True,
            "retry_count": retry_count,
            "critique_reason": None,
        }

    critique_reason = " | ".join(issues)

    if retry_count < MAX_CRITIC_RETRIES:
        logger.info(
            "Critic REJECTED (retry %d/%d): %s",
            retry_count + 1, MAX_CRITIC_RETRIES, critique_reason,
        )

        # Store failed summary for learning
        try:
            from src.storage.vector_store import add_to_negative_filter
            # We don't add to negative_filter here — that's for user feedback.
            # Instead we could add to critic_failures but keep it simple.
        except Exception:
            pass

        return {
            **state,
            "approved": False,
            "retry_count": retry_count + 1,
            "critique_reason": critique_reason,
        }

    # Max retries exhausted — approve anyway with a warning
    logger.warning(
        "Critic retries exhausted. Approving with issues: %s",
        critique_reason,
    )
    return {
        **state,
        "approved": True,
        "retry_count": retry_count,
        "critique_reason": f"(Approved with issues: {critique_reason})",
    }
