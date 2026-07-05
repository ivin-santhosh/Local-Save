"""
LinkSync AI — Report Generator
================================
Generates a markdown report summarizing synced tabs, including stats,
and saves it to the local system under data/reports.
"""

from datetime import datetime
import logging
from pathlib import Path
from config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def generate_report(results: list[dict]) -> Path:
    """
    Generate a markdown report of the synced tabs and save it locally.

    Args:
        results: List of dicts representing tab processing results.

    Returns:
        Path to the saved report file.
    """
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    display_time = now.strftime("%Y-%m-%d %H:%M:%S")

    reports_dir = PROJECT_ROOT / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / f"report_{timestamp_str}.md"

    # Calculate stats
    summarized = sum(1 for r in results if r.get("status") == "summarized")
    dispatched = sum(1 for r in results if r.get("dispatched"))
    skipped = sum(1 for r in results if r.get("status") in ("aborted", "skipped", "blacklisted"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    total = len(results)

    lines = []
    lines.append("# LinkSync AI — Sync Report")
    lines.append(f"**Generated on**: `{display_time}`\n")
    lines.append("## Sync Statistics")
    lines.append(f"- **Total Tabs**: {total}")
    lines.append(f"- **Successfully Summarized**: {summarized} ✅")
    lines.append(f"- **Dispatched to WhatsApp**: {dispatched} 📤")
    if skipped > 0:
        lines.append(f"- **Skipped (Blacklisted/Short)**: {skipped} ⏭️")
    if failed > 0:
        lines.append(f"- **Failed**: {failed} ❌")
    lines.append("\n" + "—" * 20 + "\n")
    lines.append("## Tab Details\n")

    for idx, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        domain = r.get("domain", "")
        browser = r.get("browser", "Unknown Browser")
        status = r.get("status", "unknown")
        summary = r.get("summary", "")
        dispatched_status = "Yes 📤" if r.get("dispatched") else "No ❌"

        lines.append(f"### {idx}. {title}")
        lines.append(f"- **Browser**: {browser}")
        if domain:
            lines.append(f"- **Domain**: {domain}")
        if url:
            lines.append(f"- **URL**: [{url}]({url})")
        lines.append(f"- **Status**: `{status.upper()}`")
        lines.append(f"- **Dispatched to WhatsApp**: {dispatched_status}")
        
        if summary:
            lines.append("\n**Summary**:")
            # Use safe replace for newline formatting
            formatted_summary = "\n> ".join(summary.split("\n"))
            lines.append(f"> {formatted_summary}")
        else:
            reason = r.get("skip_reason", "No content or error during processing.")
            lines.append(f"- **Note**: {reason}")
        
        lines.append("\n" + "—" * 10 + "\n")

    content = "\n".join(lines)

    try:
        report_path.write_text(content, encoding="utf-8")
        logger.info("Report saved to %s", report_path)
    except Exception as exc:
        logger.error("Failed to write report file: %s", exc)

    return report_path
