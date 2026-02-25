"""Tests for search tool provider factory."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.tools import factory as f
from foreign_query_agent.tools.mock_tool import MockSearchTool


class _DummyTavily:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _DummyBocha:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("missing")
        self.api_key = api_key


class _DummyZhipu:
    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key or not base_url or not model:
            raise ValueError("missing")
        self.api_key = api_key


class _DummyVolcano:
    def __init__(self, api_key: str, base_url: str, model_endpoint: str):
        if not api_key or not base_url or not model_endpoint:
            raise ValueError("missing")
        self.api_key = api_key
        self.model_endpoint = model_endpoint


class _DummyExa:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("missing")
        self.api_key = api_key


def test_provider_label_routes_to_expected_tool(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "BochaSearchTool", _DummyBocha)
    monkeypatch.setattr(f, "ZhipuSearchTool", _DummyZhipu)
    monkeypatch.setattr(f, "VolcEngineSearchTool", _DummyVolcano)
    monkeypatch.setattr(f, "ExaSearchTool", _DummyExa)

    assert isinstance(
        f.create_search_tool("Bocha Search", fallback_tavily_key="tv", bocha_api_key="bk"),
        _DummyBocha,
    )
    assert isinstance(
        f.create_search_tool(
            "Zhipu Web Search",
            fallback_tavily_key="tv",
            zhipu_api_key="zk",
            zhipu_openai_base_url="https://open.bigmodel.cn/api/paas/v4/",
            zhipu_web_search_model="glm-4-plus",
        ),
        _DummyZhipu,
    )
    assert isinstance(
        f.create_search_tool(
            "Volcano Engine",
            fallback_tavily_key="tv",
            volcengine_api_key="vk",
            volcengine_openai_base_url="https://ark.cn-beijing.volces.com/api/v3",
            volcengine_model_ep="ep-123",
        ),
        _DummyVolcano,
    )
    assert isinstance(
        f.create_search_tool("Exa Search", fallback_tavily_key="tv", exa_api_key="ek"),
        _DummyExa,
    )


def test_missing_provider_key_falls_back_to_tavily(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "BochaSearchTool", _DummyBocha)

    tool = f.create_search_tool("Bocha Search", fallback_tavily_key="tv", bocha_api_key="")
    assert isinstance(tool, _DummyTavily)
    assert tool.api_key == "tv"


def test_unknown_or_legacy_label_falls_back_to_tavily(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)

    assert isinstance(f.create_search_tool("unknown provider", fallback_tavily_key="tv"), _DummyTavily)
    assert isinstance(f.create_search_tool("Serper (Google)", fallback_tavily_key="tv"), _DummyTavily)
    assert isinstance(f.create_search_tool("Bing Search", fallback_tavily_key="tv"), _DummyTavily)


def test_provider_and_tavily_fail_then_fallback_to_mock(monkeypatch):
    class _BrokenTool:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("broken")

    monkeypatch.setattr(f, "TavilySearchTool", _BrokenTool)
    monkeypatch.setattr(f, "BochaSearchTool", _BrokenTool)

    tool = f.create_search_tool("Bocha Search", fallback_tavily_key="tv", bocha_api_key="bk")
    assert isinstance(tool, MockSearchTool)
