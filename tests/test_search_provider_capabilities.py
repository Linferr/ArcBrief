"""Provider capability metadata tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.tools import factory as f


class _DummyTavily:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _DummyBocha:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _DummyExa:
    def __init__(self, api_key: str):
        self.api_key = api_key


class _DummyZhipu:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model


class _DummyVolcano:
    def __init__(self, api_key: str, base_url: str, model_endpoint: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_endpoint = model_endpoint


def test_provider_capability_flags(monkeypatch):
    monkeypatch.setattr(f, "TavilySearchTool", _DummyTavily)
    monkeypatch.setattr(f, "BochaSearchTool", _DummyBocha)
    monkeypatch.setattr(f, "ExaSearchTool", _DummyExa)
    monkeypatch.setattr(f, "ZhipuSearchTool", _DummyZhipu)
    monkeypatch.setattr(f, "VolcEngineSearchTool", _DummyVolcano)

    _, zhipu_meta = f.create_search_tool_with_meta(
        "Zhipu Web Search",
        zhipu_api_key="zk",
        zhipu_openai_base_url="https://open.bigmodel.cn/api/paas/v4/",
        zhipu_web_search_model="glm-4-plus",
    )
    assert zhipu_meta.openai_compatible is True
    assert zhipu_meta.llm_assisted_search is True
    assert zhipu_meta.api_style == "openai_compatible"

    _, volcano_meta = f.create_search_tool_with_meta(
        "Volcano Engine",
        volcengine_api_key="vk",
        volcengine_openai_base_url="https://ark.cn-beijing.volces.com/api/v3",
        volcengine_model_ep="ep-123",
    )
    assert volcano_meta.openai_compatible is True
    assert volcano_meta.llm_assisted_search is True
    assert volcano_meta.api_style == "openai_compatible"

    _, exa_meta = f.create_search_tool_with_meta("Exa Search", exa_api_key="ek", fallback_tavily_key="tv")
    _, bocha_meta = f.create_search_tool_with_meta("Bocha Search", bocha_api_key="bk", fallback_tavily_key="tv")
    _, tavily_meta = f.create_search_tool_with_meta("Tavily Search API", fallback_tavily_key="tv")
    assert exa_meta.llm_assisted_search is False and exa_meta.openai_compatible is False
    assert bocha_meta.llm_assisted_search is False and bocha_meta.openai_compatible is False
    assert tavily_meta.llm_assisted_search is False and tavily_meta.openai_compatible is False
