"""Run fail-fast behavior when strict provider is unavailable."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from backend.state import RunRecord
from foreign_query_agent.tools import factory as f


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.llm_model = "qwen3-max"
        self.search_provider = "Volcano Engine"
        self.research_strict_provider = True
        self.research_recency_mode = "recent_12m_with_90d_anchor"
        self.max_reflections = 3
        self.llm_api_key = "dummy"
        self.llm_base_url = "http://dummy"
        self.tavily_api_key = "tv"
        self.bocha_api_key = ""
        self.zhipu_api_key = ""
        self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.zhipu_web_search_model = "glm-4-plus"
        self.exa_api_key = ""
        self.volcengine_api_key = "vk"
        self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.volcengine_model_ep = "ep-123"


class _FailFastAgent:
    def __init__(self, settings):
        raise f.ProviderUnavailableError(
            "Volcano unavailable",
            f.SearchToolBuildMeta(
                provider_requested="Volcano Engine",
                provider_effective="Unavailable",
                fallback_reason="Volcano Engine unavailable: package is not installed.",
            ),
        )


class _DummyDB:
    def __init__(self):
        self.saved = []

    def get_app_config(self):
        return {
            "search_provider": "Volcano Engine",
            "primary_model": "Qwen3 MAX",
            "critical_analysis_layer": True,
        }

    def save_research_run(self, **kwargs):
        self.saved.append(kwargs)


def test_run_job_fails_fast_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _FailFastAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])
    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-provider-failfast"
    m.RUNS[run_id] = RunRecord(run_id=run_id, query="latest model workflow")
    try:
        m._run_job(run_id=run_id, query="latest model workflow", language="English (US)")
        record = m.RUNS[run_id]
        assert record.status == "failed"
        assert "PROVIDER_UNAVAILABLE" in (record.report_content or "")
        assert any("PROVIDER_UNAVAILABLE" in event.message for event in record.events)
    finally:
        m.RUNS.pop(run_id, None)
