"""System status provider probe tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from foreign_query_agent.tools import factory as f


def test_system_status_returns_unavailable_when_probe_fails(monkeypatch):
    class _ProbeDB:
        def get_app_config(self):
            return {"search_provider": "Volcano Engine", "critical_analysis_layer": True}

    class _ProbeSettings:
        def __init__(self, output_dir: str = "outputs"):
            self.output_dir = output_dir
            self.research_strict_provider = True
            self.search_provider = "Volcano Engine"
            self.tavily_api_key = "tv"
            self.bocha_api_key = ""
            self.zhipu_api_key = ""
            self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
            self.zhipu_web_search_model = "glm-4-plus"
            self.exa_api_key = ""
            self.volcengine_api_key = "vk"
            self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
            self.volcengine_model_ep = "ep-123"

    def _probe_factory(*args, **kwargs):
        raise f.ProviderUnavailableError(
            "Volcano unavailable",
            f.SearchToolBuildMeta(
                provider_requested="Volcano Engine",
                provider_effective="Unavailable",
                fallback_reason="Volcano Engine unavailable: endpoint rejected",
            ),
        )

    monkeypatch.setattr(m, "DB", _ProbeDB())
    monkeypatch.setattr(m, "SCHEDULER", None)
    monkeypatch.setattr(m, "Settings", _ProbeSettings)
    monkeypatch.setattr(m, "create_search_tool_with_meta", _probe_factory)

    status = m.system_status()
    assert status["search_provider_configured"] == "Volcano Engine"
    assert status["search_provider_effective"] == "Unavailable"
    assert status["search_provider_fallback"] != ""
    assert status["search_llm_assisted"] is False


def test_system_status_returns_effective_provider_when_probe_succeeds(monkeypatch):
    class _ProbeDB:
        def get_app_config(self):
            return {"search_provider": "Zhipu Web Search", "critical_analysis_layer": True}

    class _ProbeSettings:
        def __init__(self, output_dir: str = "outputs"):
            self.output_dir = output_dir
            self.research_strict_provider = True
            self.search_provider = "Zhipu Web Search"
            self.tavily_api_key = "tv"
            self.bocha_api_key = ""
            self.zhipu_api_key = "zk"
            self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
            self.zhipu_web_search_model = "glm-4-plus"
            self.exa_api_key = ""
            self.volcengine_api_key = ""
            self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
            self.volcengine_model_ep = ""

    def _probe_factory(*args, **kwargs):
        return object(), f.SearchToolBuildMeta(
            provider_requested="Zhipu Web Search",
            provider_effective="Zhipu Web Search",
            fallback_reason="",
            llm_assisted_search=True,
        )

    monkeypatch.setattr(m, "DB", _ProbeDB())
    monkeypatch.setattr(m, "SCHEDULER", None)
    monkeypatch.setattr(m, "Settings", _ProbeSettings)
    monkeypatch.setattr(m, "create_search_tool_with_meta", _probe_factory)

    status = m.system_status()
    assert status["search_provider_configured"] == "Zhipu Web Search"
    assert status["search_provider_effective"] == "Zhipu Web Search"
    assert status["search_provider_fallback"] == ""
    assert status["search_llm_assisted"] is True
