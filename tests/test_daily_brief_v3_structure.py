"""Daily Brief V3 structure tests."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.briefing as briefing


def _sample_items():
    return [
        {
            "title": "Karpathy discusses agentic engineering",
            "url": "https://example.com/karpathy-agentic",
            "content": "He shared concrete workflow advice, evaluation checkpoints, and constraints.",
            "source": "example.com",
            "published_at": "2026-02-22T11:00:00",
        },
        {
            "title": "New coding workflow templates",
            "url": "https://example.com/template-pack",
            "content": "The update includes CLAUDE.md and .cursorrules examples.",
            "source": "example.com",
            "published_at": "2026-02-21T08:30:00",
        },
    ]


def test_daily_brief_v3_contains_required_sections_and_source_refs(monkeypatch):
    topic = SimpleNamespace(name="AI Builder Signals", keywords=["agentic", "workflow", "template"])
    monkeypatch.setattr(briefing, "_get_llm", lambda: None)

    result = briefing.build_brief_for_topic(
        topic,
        _sample_items(),
        app_config={"report_language": "English (US)"},
    )

    assert "## 📌 Core TL;DR" in result
    assert "## 📂 Thematic Clusters" in result
    assert "## 💡 Insights" in result
    assert "## Sources" in result
    assert "(C1)" in result
