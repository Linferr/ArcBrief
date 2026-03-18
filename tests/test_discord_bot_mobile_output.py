"""Discord bot mobile-first output formatting tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot_formatting import (
    format_analyze_mobile_message,
    format_ask_mobile_message,
    format_bookmark_action_message,
    format_brief_mobile_message,
    format_digest_mobile_message,
    format_long_task_status_message,
    format_research_mobile_message,
    format_saved_mobile_message,
    format_tldr_mobile_message,
)


def test_format_brief_mobile_message_prioritizes_summary_over_full_markdown():
    brief = {
        "id": 42,
        "topic_name": "AI Daily",
        "date": "2026-03-06",
        "content": """# 2026-03-06 AI Daily Daily Brief

## 📌 Core TL;DR
Model launches and agent tooling updates dominated today's cycle, with faster release cadence and clearer enterprise packaging.

## 📂 Thematic Clusters

### 🧠 Model Capability & Product Launches
**Key Takeaways**
- GPT shipping cadence accelerated across vendors
- Agent toolchains are becoming more standardized

## Sources
- OpenAI release note
- Anthropic changelog
- LangChain docs
""",
    }

    message = format_brief_mobile_message(brief)

    assert "AI Daily" in message
    assert "Brief ID: 42" in message
    assert "TL;DR" in message
    assert "Key points" in message
    assert "Sources: 3" in message
    assert "/ask brief_id:42" in message
    assert "```" not in message
    assert "Thematic Clusters" not in message


def test_format_digest_mobile_message_builds_compact_topic_list():
    items = [
        {
            "id": 12,
            "topic_name": "AI Daily",
            "date": "2026-03-06",
            "content": "## 📌 Core TL;DR\nModel launches dominated the day.\n\n## Sources\n- A",
        },
        {
            "id": 13,
            "topic_name": "Global Trending",
            "date": "2026-03-06",
            "content": "## 📌 Core TL;DR\nTrade negotiations remain unstable across regions.\n\n## Sources\n- A\n- B",
        },
    ]

    message = format_digest_mobile_message(items)

    assert "**Daily Digest**" in message
    assert "[12] AI Daily" in message
    assert "[13] Global Trending" in message
    assert "Model launches dominated the day." in message
    assert "Trade negotiations remain unstable" in message
    assert "Follow-up: use /ask brief_id:<id>" in message
    assert "```" not in message


def test_format_ask_mobile_message_keeps_reply_short_and_shows_context_layer():
    result = {
        "reply": "OpenAI shipped a smaller model update this week and emphasized lower-latency agent workflows.",
        "sources": ["2026-03-06 AI Daily", "2026-03-05 AI Builder Signals"],
        "context_layer": "brief_context",
        "brief_id_used": 42,
        "context_warning": "brief unavailable, fallback to general context",
    }

    message = format_ask_mobile_message(result)

    assert "Context: brief_context" in message
    assert "Brief anchor: #42" in message
    assert "Warning: brief unavailable, fallback to general context" in message
    assert "Sources: 2" in message
    assert "OpenAI shipped a smaller model update" in message
    assert "```" not in message


def test_format_research_mobile_message_returns_compact_completion_summary():
    report = """# Report

## Latest Viewpoints
MCP support is moving from experimental integrations to default infrastructure across major AI tooling vendors. Ecosystem adoption is uneven, but the direction is clear.

## Actionable Tactics
- Validate authentication and timeout handling early.

## Sources
- [S1] Anthropic -- https://a.test
- [S2] OpenRouter -- https://b.test
"""

    message = format_research_mobile_message(
        run_id="run_123",
        query="latest MCP developments",
        language="English (US)",
        report=report,
        brief_id=42,
    )

    assert "Research complete" in message
    assert "run_123" in message
    assert "latest MCP developments" in message
    assert "Sources: 2" in message
    assert "Brief anchor: #42" in message
    assert "Latest Viewpoints" in message
    assert "```" not in message


def test_format_tldr_mobile_message_shows_cache_and_domain():
    message = format_tldr_mobile_message(
        {
            "title": "OpenAI launches new agent workflow",
            "summary": "The article explains how lower-latency agent orchestration is being packaged into a simpler developer workflow.",
            "source_domain": "example.com",
            "cached": True,
        }
    )

    assert "TL;DR" in message
    assert "OpenAI launches new agent workflow" in message
    assert "Source: example.com" in message
    assert "Cached: yes" in message


def test_format_analyze_mobile_message_returns_pm_friendly_summary():
    report = """## Product Overview
Codex is being positioned as a developer-facing AI workflow product.

## Business Model
Usage-based API access and enterprise workflow integration appear central.

## Competitive Landscape
Competition is intensifying across Claude Code, Cursor, and OpenCode.
"""

    message = format_analyze_mobile_message(
        run_id="analyze_123",
        subject="OpenAI Codex",
        language="English (US)",
        report=report,
        brief_id=42,
    )

    assert "Analysis complete" in message
    assert "analyze_123" in message
    assert "OpenAI Codex" in message
    assert "Section: Product Overview" in message
    assert "Brief anchor: #42" in message
    assert "developer-facing AI workflow product" in message
    assert "```" not in message


def test_format_long_task_status_message_handles_running_and_done_states():
    running = format_long_task_status_message(kind="research", run_id="run_123", status="running")
    finished = format_long_task_status_message(kind="analyze", run_id="run_456", status="done")

    assert "Research is still running in the background." in running
    assert "run_123" in running
    assert "Analysis finished, but no report content is available yet." in finished
    assert "run_456" in finished


def test_format_saved_mobile_message_handles_empty_state():
    message = format_saved_mobile_message([])
    assert message == "No saved briefs yet."


def test_format_saved_mobile_message_lists_saved_briefs():
    message = format_saved_mobile_message(
        [
            {
                "brief_id": 12,
                "topic_name": "AI Daily",
                "date": "2026-03-07",
                "note": "watch this",
            },
            {
                "brief_id": 9,
                "topic_name": "Global Trending",
                "date": "2026-03-06",
                "note": "",
            },
        ]
    )

    assert "**Saved Briefs**" in message
    assert "[12] AI Daily (2026-03-07)" in message
    assert "note: watch this" in message
    assert "[9] Global Trending (2026-03-06)" in message


def test_format_bookmark_action_message_shows_save_and_delete_state():
    saved = format_bookmark_action_message("saved", brief_id=12, note="watch this")
    deleted = format_bookmark_action_message("deleted", brief_id=12)

    assert "Saved brief 12" in saved
    assert "watch this" in saved
    assert "Removed saved brief 12" in deleted

