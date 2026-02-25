"""Strict provider mode tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.tools import factory as f


class _DummyTavily:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _BrokenZhipu:
    def __init__(self, api_key: str, base_url: str, model: str):
        raise RuntimeError("zhipu sdk unavailable")


def test_strict_mode_raises_unavailable_without_tavily_fallback(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "ZhipuSearchTool", _BrokenZhipu)

    try:
        f.create_search_tool_with_meta(
            "Zhipu Web Search",
            fallback_tavily_key="tv",
            zhipu_api_key="zk",
            zhipu_openai_base_url="https://open.bigmodel.cn/api/paas/v4/",
            zhipu_web_search_model="glm-4-plus",
            strict=True,
        )
        assert False, "Expected ProviderUnavailableError"
    except f.ProviderUnavailableError as exc:
        assert exc.meta.provider_effective == "Unavailable"
        assert "unavailable" in exc.meta.fallback_reason.lower()


def test_non_strict_mode_keeps_legacy_tavily_fallback(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "ZhipuSearchTool", _BrokenZhipu)

    tool, meta = f.create_search_tool_with_meta(
        "Zhipu Web Search",
        fallback_tavily_key="tv",
        zhipu_api_key="zk",
        zhipu_openai_base_url="https://open.bigmodel.cn/api/paas/v4/",
        zhipu_web_search_model="glm-4-plus",
        strict=False,
    )
    assert isinstance(tool, _DummyTavily)
    assert meta.provider_effective == "Tavily Search API"
    assert meta.fallback_reason != ""
