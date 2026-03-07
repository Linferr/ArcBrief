"""OpenAI-compatible search tool adapter tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import foreign_query_agent.tools.openai_compat_search as oc


def test_openai_compat_client_uses_base_url_and_maps_results(monkeypatch):
    captured = {}

    class _Resp:
        def model_dump(self):
            return {
                "choices": [
                    {
                        "message": {
                            "annotations": [
                                {"title": "A", "url": "https://a.test", "content": "alpha"},
                                {"name": "B", "link": "https://b.test", "summary": "beta"},
                            ]
                        }
                    }
                ]
            }

    class _Chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                captured["request"] = kwargs
                return _Resp()

    class _DummyOpenAI:
        def __init__(self, api_key: str, base_url: str):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            self.chat = _Chat()

    monkeypatch.setattr(oc, "OpenAI", _DummyOpenAI)

    client = oc.OpenAICompatWebSearchClient(
        provider_name="Zhipu Web Search",
        api_key="zk",
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        model="glm-4-plus",
    )
    response = client.search("karpathy latest", max_results=2)

    assert captured["base_url"] == "https://open.bigmodel.cn/api/paas/v4/"
    assert captured["request"]["model"] == "glm-4-plus"
    assert len(response.results) == 2
    assert response.results[0].url == "https://a.test"
    assert response.results[1].url == "https://b.test"


def test_provider_tools_delegate_to_openai_compat_client(monkeypatch):
    import foreign_query_agent.tools.zhipu_tool as zt
    import foreign_query_agent.tools.volcengine_tool as vt

    class _DummyClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def search(self, query: str, max_results: int = 5):
            from foreign_query_agent.tools.base import SearchResponse

            return SearchResponse(query=query, results=[])

    monkeypatch.setattr(zt, "OpenAICompatWebSearchClient", _DummyClient)
    monkeypatch.setattr(vt, "OpenAICompatWebSearchClient", _DummyClient)

    z_tool = zt.ZhipuSearchTool(
        api_key="zk",
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        model="glm-4-plus",
    )
    v_tool = vt.VolcEngineSearchTool(
        api_key="vk",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model_endpoint="ep-123",
    )

    assert z_tool.client.kwargs["provider_name"] == "Zhipu Web Search"
    assert v_tool.client.kwargs["provider_name"] == "Volcano Engine"


def test_openai_compat_plain_chat_sets_degraded_metadata(monkeypatch):
    captured = {}

    class _Resp:
        def model_dump(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Plain chat answer without citations.",
                        }
                    }
                ]
            }

    class _Chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                captured["request"] = kwargs
                return _Resp()

    class _DummyOpenAI:
        def __init__(self, api_key: str, base_url: str):
            self.chat = _Chat()

    monkeypatch.setattr(oc, "OpenAI", _DummyOpenAI)

    client = oc.OpenAICompatWebSearchClient(
        provider_name="Volcano Engine",
        api_key="vk",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-123",
        search_mode="plain_chat",
    )
    response = client.search("mcp latest", max_results=1)

    assert "tools" not in captured["request"]
    assert response.results[0].url == ""
    assert client.search_mode == "plain_chat"
