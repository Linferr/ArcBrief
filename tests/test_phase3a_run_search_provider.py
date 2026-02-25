"""Tests for search_provider propagation in _run_job."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from backend.state import RunRecord


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.llm_model = "qwen3-max"
        self.search_provider = "Tavily Search API"
        self.max_reflections = 3
        self.llm_api_key = "dummy"
        self.llm_base_url = "http://dummy"
        self.tavily_api_key = "tv"
        self.bocha_api_key = ""
        self.zhipu_api_key = ""
        self.exa_api_key = ""
        self.volcengine_api_key = ""
        self.volcengine_model_ep = ""


class _DummyQueryAgent:
    last_settings = None

    def __init__(self, settings):
        _DummyQueryAgent.last_settings = settings

    def research(self, query, progress_cb=None, language="English (US)"):
        if progress_cb:
            progress_cb({"stage": "outline", "message": "Outline generated", "run_id": "unit"})
        return f"report:{query}:{language}"

    def save_report(self, report, output_dir):
        return f"{output_dir}/report.md"


class _DummyDB:
    def __init__(self, search_provider: str):
        self.search_provider = search_provider
        self.saved_runs = []

    def get_app_config(self):
        return {
            "search_provider": self.search_provider,
            "primary_model": "Qwen3 MAX",
            "critical_analysis_layer": True,
        }

    def save_research_run(self, **kwargs):
        self.saved_runs.append(kwargs)


def test_run_job_injects_search_provider_and_keeps_language(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _DummyQueryAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])

    db = _DummyDB(search_provider="Bocha Search")
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-run-provider"
    m.RUNS[run_id] = RunRecord(run_id=run_id, query="latest ai toolchain")
    try:
        m._run_job(run_id=run_id, query="latest ai toolchain", language="Chinese (Simplified)")
        record = m.RUNS[run_id]
        assert record.status == "done"
        assert record.language_used == "Chinese (Simplified)"
        assert _DummyQueryAgent.last_settings is not None
        assert _DummyQueryAgent.last_settings.search_provider == "Bocha Search"
        assert db.saved_runs and db.saved_runs[-1]["language_used"] == "Chinese (Simplified)"
    finally:
        m.RUNS.pop(run_id, None)
