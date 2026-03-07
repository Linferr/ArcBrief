"""Tests for Phase 4B /api/analyze mode."""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as main
from backend.state import RUNS, RunRecord


def test_build_analyze_query_contains_pm_dimensions():
    query = main._build_analyze_query("OpenAI Codex")

    assert "OpenAI Codex" in query
    assert "Product Overview" in query
    assert "Business Model" in query
    assert "Competitive Landscape" in query
    assert "SWOT" in query
    assert "User & Market" in query
    assert "Strategic Watchpoints" in query


def test_run_job_analyze_mode_rewrites_report(monkeypatch):
    run_id = "analyze_test"
    RUNS[run_id] = RunRecord(run_id=run_id, query="OpenAI Codex", run_type="analyze")

    class DummyAgent:
        def __init__(self, settings):
            self.search_meta = SimpleNamespace(
                provider_requested="Tavily Search API",
                provider_effective="Tavily Search API",
                fallback_reason="",
                llm_assisted_search=False,
            )

        def research(self, query, progress_cb=None, language="English (US)"):
            return "# Report\n\n## Latest Viewpoints\nRaw analysis body."

        def save_report(self, report, output_dir):
            return os.path.join(output_dir, "analyze_test.md")

    monkeypatch.setattr(main, "QueryAgent", DummyAgent)
    monkeypatch.setattr(main, "DB", SimpleNamespace(get_app_config=lambda: {}, save_research_run=lambda **kwargs: None))
    monkeypatch.setattr(
        main,
        "llm_chat",
        lambda system, user: (
            "## Product Overview\nA\n\n"
            "## Business Model\nB\n\n"
            "## Competitive Landscape\nC\n\n"
            "## SWOT\nD\n\n"
            "## User & Market\nE\n\n"
            "## Strategic Watchpoints\nF"
        ),
    )

    try:
        main._run_job(run_id, "OpenAI Codex", "English (US)", run_type="analyze")
        record = RUNS[run_id]
        assert record.status == "done"
        assert "## Product Overview" in (record.report_content or "")
        assert "## Strategic Watchpoints" in (record.report_content or "")
    finally:
        RUNS.pop(run_id, None)
