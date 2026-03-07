"""Provider-check endpoint status classification tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from foreign_query_agent.tools.base import SearchResponse, SearchTool
from foreign_query_agent.tools.factory import SearchToolBuildMeta


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.tavily_api_key = "tv"
        self.bocha_api_key = "bk"
        self.zhipu_api_key = "zk"
        self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.zhipu_web_search_model = "glm-4-plus"
        self.exa_api_key = "ek"
        self.volcengine_api_key = "vk"
        self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.volcengine_model_ep = "ep-123"


class _ObservedTool(SearchTool):
    def __init__(
        self,
        *,
        results_count: int = 0,
        last_error_class: str = "",
        last_error_message: str = "",
        search_mode: str = "search_api",
        urls_present: bool = True,
    ):
        self.results_count = results_count
        self.last_error_class = last_error_class
        self.last_error_message = last_error_message
        self.search_mode = search_mode
        self.urls_present = urls_present

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        from foreign_query_agent.tools.base import SearchResult

        results = []
        for idx in range(self.results_count):
            results.append(
                SearchResult(
                    title=f"title-{idx}",
                    url=f"https://x.test/{idx}" if self.urls_present else "",
                    content=f"body-{idx}",
                )
            )
        return SearchResponse(query=query, results=results)


def test_provider_check_surfaces_tool_error_class(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)

    def _factory(provider_name: str, strict: bool = True, **kwargs):
        tool = _ObservedTool(
            results_count=0,
            last_error_class="request_schema_error",
            last_error_message="MissingParameter tools.function",
        )
        meta = SearchToolBuildMeta(
            provider_requested=provider_name,
            provider_effective=provider_name,
        )
        return tool, meta

    monkeypatch.setattr(m, "create_search_tool_with_meta", _factory)

    payload = m.provider_check()
    first = payload["providers"][0]
    assert first["status"] == "request_schema_error"
    assert "MissingParameter" in first["error_detail"]
    assert first["search_mode"] == "search_api"


def test_provider_check_marks_plain_chat_without_urls_as_degraded(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)

    def _factory(provider_name: str, strict: bool = True, **kwargs):
        tool = _ObservedTool(
            results_count=1,
            search_mode="plain_chat",
            urls_present=False,
        )
        meta = SearchToolBuildMeta(
            provider_requested=provider_name,
            provider_effective=provider_name,
        )
        return tool, meta

    monkeypatch.setattr(m, "create_search_tool_with_meta", _factory)

    payload = m.provider_check()
    first = payload["providers"][0]
    assert first["status"] == "degraded_plain_chat"
    assert first["result_count"] == 1
    assert first["search_mode"] == "plain_chat"
