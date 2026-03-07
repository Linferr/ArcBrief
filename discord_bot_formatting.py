"""Mobile-first formatting helpers for Discord bot output."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_BRIEF_CORE_HEADERS = (
    "## 📌 Core TL;DR",
    "## TL;DR",
    "## 今日核心",
    "## 📌 今日核心 (TL;DR)",
    "## 📌 今日核心",
)
_BRIEF_SOURCES_HEADERS = (
    "## Sources",
    "## 来源",
    "## 来源索引",
    "## ソース",
    "## ソース索引",
)
_RESEARCH_SECTION_HEADERS = (
    "## Latest Viewpoints",
    "## 最新观点",
    "## 最新の見解",
)
_ANALYZE_SECTION_HEADERS = (
    "## Product Overview",
    "## 产品概览",
    "## 製品概要",
)


def _truncate(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _strip_markdown(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^#+\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"[*_`>~]", "", value)
    value = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_section(text: str, headers: tuple[str, ...]) -> str:
    lines = (text or "").splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line in headers:
            buf: List[str] = []
            for nxt in lines[i + 1 :]:
                stripped = nxt.strip()
                if stripped.startswith("## "):
                    break
                buf.append(nxt)
            return "\n".join(buf).strip()
    return ""


def _extract_title(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_key_points(text: str, limit: int = 3) -> List[str]:
    points: List[str] = []
    capture = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        lowered = line.lower()
        if "key takeaways" in lowered or "关键要点" in line or line == "要点":
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and (line.startswith("- ") or line.startswith("* ")):
            points.append(_truncate(_strip_markdown(line[2:]), 110))
        if len(points) >= limit:
            break
    return points


def _count_sources(text: str) -> int:
    sources = _extract_section(text, _BRIEF_SOURCES_HEADERS)
    return sum(1 for line in sources.splitlines() if line.strip().startswith("- "))


def _extract_first_paragraph(text: str) -> str:
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        cleaned = _strip_markdown(block)
        if cleaned:
            return cleaned
    return ""


def format_brief_mobile_message(brief: Dict[str, Any]) -> str:
    content = brief.get("content", "") or ""
    title = brief.get("topic_name") or _extract_title(content) or "Latest Brief"
    date = brief.get("date", "N/A")
    brief_id = brief.get("id")
    tldr = _extract_section(content, _BRIEF_CORE_HEADERS)
    tldr_text = _truncate(_extract_first_paragraph(tldr or content), 260) or "No summary available."
    points = _extract_key_points(content)
    source_count = _count_sources(content)

    lines = [
        f"**{title}** | {date}",
        f"Brief ID: {brief_id}" if brief_id is not None else "Brief ID: unavailable",
        f"TL;DR: {tldr_text}",
    ]
    if points:
        lines.append("Key points:")
        lines.extend(f"- {point}" for point in points[:3])
    lines.append(f"Sources: {source_count}")
    return "\n".join(lines)


def format_digest_mobile_message(items: List[Dict[str, Any]]) -> str:
    lines = ["**Daily Digest**"]
    for item in items:
        summary = _extract_section(item.get("content", ""), _BRIEF_CORE_HEADERS)
        summary_text = _truncate(_extract_first_paragraph(summary or item.get("content", "")), 120)
        brief_id = item.get("id")
        lines.append(
            f"- [{brief_id if brief_id is not None else '?'}] "
            f"{item.get('topic_name', 'Unknown')} ({item.get('date', 'N/A')}): "
            f"{summary_text or 'No summary available.'}"
        )
    return "\n".join(lines)


def format_ask_mobile_message(result: Dict[str, Any]) -> str:
    reply = _truncate(result.get("reply", "No relevant information found."), 500)
    sources = result.get("sources", []) or []
    context_layer = result.get("context_layer") or result.get("source_layer")
    lines = [reply]
    if context_layer:
        lines.append(f"Context: {context_layer}")
    lines.append(f"Sources: {len(sources)}")
    return "\n".join(lines)


def format_research_mobile_message(
    *,
    run_id: str,
    query: str,
    language: str,
    report: str,
) -> str:
    section = _extract_section(report, _RESEARCH_SECTION_HEADERS)
    summary = _truncate(_extract_first_paragraph(section or report), 320) or "No summary available."
    source_count = _count_sources(report)
    lines = [
        f"**Research complete** | `{run_id}`",
        f"Query: {query}",
        f"Language: {language}",
        "Section: Latest Viewpoints",
        summary,
        f"Sources: {source_count}",
        "Full report is available in the web UI or via the status API.",
    ]
    return "\n".join(lines)


def format_analyze_mobile_message(
    *,
    run_id: str,
    subject: str,
    language: str,
    report: str,
) -> str:
    section = _extract_section(report, _ANALYZE_SECTION_HEADERS)
    summary = _truncate(_extract_first_paragraph(section or report), 320) or "No summary available."
    lines = [
        f"**Analysis complete** | `{run_id}`",
        f"Subject: {subject}",
        f"Language: {language}",
        "Section: Product Overview",
        summary,
        "Full analysis is available in the web UI or via the status API.",
    ]
    return "\n".join(lines)


def format_long_task_status_message(*, kind: str, run_id: str, status: str) -> str:
    label = "Analysis" if kind == "analyze" else "Research"
    normalized = (status or "running").lower()
    if normalized == "done":
        return (
            f"{label} finished, but no report content is available yet.\n"
            f"Run ID: `{run_id}`\n"
            f"Check the web UI or `/api/status/{run_id}` for the final report."
        )
    if normalized == "error":
        return (
            f"{label} failed before producing report content.\n"
            f"Run ID: `{run_id}`\n"
            f"Check the web UI or `/api/status/{run_id}` for details."
        )
    return (
        f"{label} is still running in the background.\n"
        f"Run ID: `{run_id}`\n"
        f"Check the web UI or `/api/status/{run_id}` for progress and the final report."
    )


def format_tldr_mobile_message(result: Dict[str, Any]) -> str:
    title = result.get("title") or "Untitled"
    summary = _truncate(result.get("summary", "No summary available."), 420)
    domain = result.get("source_domain") or "unknown"
    cached = "yes" if result.get("cached") else "no"
    lines = [
        f"**TL;DR** | {title}",
        summary,
        f"Source: {domain}",
        f"Cached: {cached}",
    ]
    return "\n".join(lines)


def format_saved_mobile_message(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No saved briefs yet."
    lines = ["**Saved Briefs**"]
    for item in items[:10]:
        line = f"- [{item.get('brief_id')}] {item.get('topic_name', 'Unknown')} ({item.get('date', 'N/A')})"
        note = (item.get("note") or "").strip()
        if note:
            line += f" — note: {note}"
        lines.append(line)
    return "\n".join(lines)


def format_bookmark_action_message(status: str, *, brief_id: int, note: Optional[str] = None) -> str:
    if status == "saved":
        base = f"Saved brief {brief_id}."
        note_text = (note or "").strip()
        return f"{base} note: {note_text}" if note_text else base
    if status == "deleted":
        return f"Removed saved brief {brief_id}."
    return f"Bookmark status: {status} ({brief_id})"


def chunk_text(text: str, size: int = 1800) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
