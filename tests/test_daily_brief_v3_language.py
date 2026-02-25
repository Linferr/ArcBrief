"""Daily Brief V3 language behavior tests."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.briefing as briefing


def _sample_items():
    return [
        {
            "title": "OpenAI ships new agent workflow",
            "url": "https://openai.com/blog/agent-workflow",
            "content": "OpenAI introduced a practical agent workflow with templates and rollout steps.",
            "source": "openai.com",
            "published_at": "2026-02-20T09:00:00",
        }
    ]


def test_daily_brief_v3_uses_chinese_layout_when_language_is_chinese(monkeypatch):
    topic = SimpleNamespace(name="AI Daily", keywords=["OpenAI", "agent", "workflow"])
    monkeypatch.setattr(briefing, "_get_llm", lambda: None)

    result = briefing.build_brief_for_topic(
        topic,
        _sample_items(),
        app_config={"report_language": "Chinese (Simplified)"},
    )

    assert "## 📌 今日核心 (TL;DR)" in result
    assert "## 📂 专题速递" in result
    assert "## 💡 趋势与洞察" in result
    assert "## 来源索引" in result
    assert "## TLDR" not in result
