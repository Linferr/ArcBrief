"""Search observability tests for Phase 3A.3."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from backend.state import RunRecord
from foreign_query_agent.tools import factory as f


class _DummyTavily:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _DummyVolcano:
    def __init__(self, api_key: str, base_url: str, model_endpoint: str):
        if not api_key or not base_url or not model_endpoint:
            raise ValueError("missing")
        self.api_key = api_key
        self.model_endpoint = model_endpoint


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.llm_model = "qwen3-max"
        self.search_provider = "Tavily Search API"
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
        self.volcengine_api_key = ""
        self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.volcengine_model_ep = ""


class _DummyAgent:
    def __init__(self, settings):
        self.settings = settings
        self.search_meta = f.SearchToolBuildMeta(
            provider_requested=settings.search_provider,
            provider_effective="Tavily Search API",
            fallback_reason="Bocha Search unavailable: missing",
            llm_assisted_search=False,
        )

    def research(self, query, progress_cb=None, language="English (US)"):
        if progress_cb:
            progress_cb({"stage": "outline", "message": "Outline generated", "run_id": "unit"})
        return f"report:{query}:{language}"

    def save_report(self, report, output_dir):
        return f"{output_dir}/report.md"


class _DummyDB:
    def __init__(self):
        self.saved_runs = []

    def get_app_config(self):
        return {
            "search_provider": "Bocha Search",
            "primary_model": "Qwen3 MAX",
            "critical_analysis_layer": True,
            "research_recency_mode": "recent_12m_with_90d_anchor",
        }

    def save_research_run(self, **kwargs):
        self.saved_runs.append(kwargs)


def test_factory_marks_volcano_as_llm_assisted(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "VolcEngineSearchTool", _DummyVolcano)

    _tool, meta = f.create_search_tool_with_meta(
        "Volcano Engine",
        fallback_tavily_key="tv",
        volcengine_api_key="vk",
        volcengine_openai_base_url="https://ark.cn-beijing.volces.com/api/v3",
        volcengine_model_ep="ep-123",
    )
    assert meta.provider_requested == "Volcano Engine"
    assert meta.provider_effective == "Volcano Engine"
    assert meta.llm_assisted_search is True
    assert meta.fallback_reason == ""


def test_factory_marks_zhipu_as_llm_assisted(monkeypatch):
    class _DummyZhipu:
        def __init__(self, api_key: str, base_url: str, model: str):
            if not api_key or not base_url or not model:
                raise ValueError("missing")
            self.api_key = api_key

    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "ZhipuSearchTool", _DummyZhipu)

    _tool, meta = f.create_search_tool_with_meta(
        "Zhipu Web Search",
        fallback_tavily_key="tv",
        zhipu_api_key="zk",
        zhipu_openai_base_url="https://open.bigmodel.cn/api/paas/v4/",
        zhipu_web_search_model="glm-4-plus",
    )
    assert meta.provider_requested == "Zhipu Web Search"
    assert meta.provider_effective == "Zhipu Web Search"
    assert meta.llm_assisted_search is True
    assert meta.fallback_reason == ""


def test_run_job_writes_search_provider_event(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _DummyAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])

    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-search-observe"
    m.RUNS[run_id] = RunRecord(run_id=run_id, query="karpathy latest tactics")
    try:
        m._run_job(run_id=run_id, query="karpathy latest tactics", language="English (US)")
        record = m.RUNS[run_id]
        stages = [event.stage for event in record.events]
        assert "search_provider" in stages
        assert record.status == "done"
        assert db.saved_runs and db.saved_runs[-1]["language_used"] == "English (US)"
        assert m._LAST_SEARCH_DIAGNOSTICS["search_provider_effective"] == "Tavily Search API"
        assert m._LAST_SEARCH_DIAGNOSTICS["search_provider_fallback"] != ""
    finally:
        m.RUNS.pop(run_id, None)


def test_run_job_uses_final_search_meta_after_runtime_fallback(monkeypatch):
    class _FallbackAgent:
        def __init__(self, settings):
            self.settings = settings
            self.search_meta = f.SearchToolBuildMeta(
                provider_requested=settings.search_provider,
                provider_effective="Volcano Engine",
                fallback_reason="",
                llm_assisted_search=True,
                openai_compatible=True,
            )

        def research(self, query, progress_cb=None, language="English (US)"):
            self.search_meta.provider_effective = "Tavily Search API"
            self.search_meta.fallback_reason = "Runtime provider fallback: Volcano Engine -> Tavily Search API due to auth_error: 403"
            if progress_cb:
                progress_cb(
                    {
                        "stage": "warning",
                        "message": self.search_meta.fallback_reason,
                        "run_id": "unit",
                    }
                )
            return f"report:{query}:{language}"

        def save_report(self, report, output_dir):
            return f"{output_dir}/report.md"

    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _FallbackAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])

    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-runtime-fallback-observe"
    m.RUNS[run_id] = RunRecord(run_id=run_id, query="karpathy latest tactics")
    try:
        m._run_job(run_id=run_id, query="karpathy latest tactics", language="English (US)")
        record = m.RUNS[run_id]
        assert record.status == "done"
        assert record.metrics_summary["provider_effective"] == "Tavily Search API"
        assert record.metrics_summary["fallback_triggered"] is True
        assert "auth_error" in record.metrics_summary["provider_fallback_reason"]
    finally:
        m.RUNS.pop(run_id, None)


def test_system_status_probes_effective_provider_from_current_config(monkeypatch):
    class _ProbeDB:
        def get_app_config(self):
            return {"search_provider": "Exa Search", "critical_analysis_layer": True}

    class _ProbeSettings:
        def __init__(self, output_dir: str = "outputs"):
            self.output_dir = output_dir
            self.search_provider = "Tavily Search API"
            self.research_strict_provider = True
            self.tavily_api_key = "tv"
            self.bocha_api_key = ""
            self.zhipu_api_key = ""
            self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
            self.zhipu_web_search_model = "glm-4-plus"
            self.exa_api_key = "exa-key"
            self.volcengine_api_key = ""
            self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
            self.volcengine_model_ep = ""

    def _probe_factory(provider_label, **kwargs):
        assert provider_label == "Exa Search"
        return object(), f.SearchToolBuildMeta(
            provider_requested="Exa Search",
            provider_effective="Exa Search",
            fallback_reason="",
            llm_assisted_search=False,
        )

    monkeypatch.setattr(m, "DB", _ProbeDB())
    monkeypatch.setattr(m, "SCHEDULER", None)
    monkeypatch.setattr(m, "Settings", _ProbeSettings)
    monkeypatch.setattr(m, "create_search_tool_with_meta", _probe_factory)

    status = m.system_status()
    assert status["search_provider_configured"] == "Exa Search"
    assert status["search_provider_effective"] == "Exa Search"
    assert status["search_provider_fallback"] == ""
    assert status["search_llm_assisted"] is False
