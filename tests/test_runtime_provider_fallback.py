import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.tools.base import SearchResponse, SearchResult
from foreign_query_agent.tools.factory import SearchToolBuildMeta


class _SingleSectionStructureNode:
    def run(self, query, language="English (US)"):
        return [{"title": "Section A", "content": f"Analyze {query}"}]


class _SingleQuerySearchPlanNode:
    def run(self, title, content, language="English (US)", recency_mode="recent_12m_with_90d_anchor"):
        return {"search_queries": [{"query": f"{title} primary evidence"}]}


class _SimpleSummaryNode:
    def run(self, title, content, search_query, search_results, language="English (US)"):
        return (
            f"{title} summary [S1]",
            {"S1": {"title": f"{title} source", "url": f"https://example.com/{title.lower().replace(' ', '-')}"}} ,
        )


class _HostPassNode:
    def run(self, title, content, latest, language="English (US)"):
        return {
            "overall_score": 4,
            "gate_decision": "PASS",
            "blocking_issues": [],
            "suggested_queries": [],
            "questions": [],
            "critique": "Ready.",
            "source_gaps": "",
        }


class _EchoFormattingNode:
    def run(self, paragraphs, language="English (US)"):
        body = "\n".join(f"## {item['title']}\n{item['content']}" for item in paragraphs)
        return f"# Report\n\n{body}"


class _AuthFailPrimaryTool:
    def __init__(self):
        self.last_error_class = ""
        self.last_error_message = ""
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        self.last_error_class = "auth_error"
        self.last_error_message = "403 AccountOverdueError"
        return SearchResponse(query=query, results=[])


class _EmptyPrimaryTool:
    def __init__(self):
        self.last_error_class = ""
        self.last_error_message = ""
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        self.last_error_class = ""
        self.last_error_message = ""
        return SearchResponse(query=query, results=[])


class _FallbackTool:
    def __init__(self):
        self.last_error_class = ""
        self.last_error_message = ""
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title=f"Fallback result for {query}",
                    url="https://example.com/fallback",
                    content="Recovered evidence from Tavily fallback.",
                )
            ],
        )


def _build_agent(primary_tool, fallback_tool=None):
    settings = Settings(output_dir=os.path.join(ROOT, "_test_outputs"))
    settings.mock_mode = True
    settings.max_parallel_sections = 1
    settings.max_reflections = 1
    agent = QueryAgent(settings)
    agent.structure_node = _SingleSectionStructureNode()
    agent.search_node = _SingleQuerySearchPlanNode()
    agent.summary_node = _SimpleSummaryNode()
    agent.host_node = _HostPassNode()
    agent.formatting_node = _EchoFormattingNode()
    agent.tool = primary_tool
    agent.search_meta = SearchToolBuildMeta(
        provider_requested="Volcano Engine",
        provider_effective="Volcano Engine",
        fallback_reason="",
        llm_assisted_search=True,
        openai_compatible=True,
        api_style="openai_compatible",
    )
    agent.runtime_fallback_tool = fallback_tool
    agent.runtime_fallback_meta = (
        SearchToolBuildMeta(
            provider_requested="Volcano Engine",
            provider_effective="Tavily Search API",
            fallback_reason="",
            llm_assisted_search=False,
            openai_compatible=False,
            api_style="search_api",
        )
        if fallback_tool is not None
        else None
    )
    return agent


def test_runtime_fallback_uses_tavily_on_auth_error():
    primary = _AuthFailPrimaryTool()
    fallback = _FallbackTool()
    agent = _build_agent(primary, fallback)
    events = []

    report = agent.research("Industrial agent readiness", progress_cb=events.append)

    assert "# Report" in report
    assert primary.queries == ["Section A latest 90 days 2026", "Section A primary evidence"]
    assert fallback.queries == ["Section A latest 90 days 2026", "Section A primary evidence"]
    assert agent.search_meta.provider_effective == "Tavily Search API"
    assert "auth_error" in agent.search_meta.fallback_reason
    assert "403" in agent.search_meta.fallback_reason
    assert any(evt["stage"] == "warning" and "runtime provider fallback" in evt["message"].lower() for evt in events)


def test_runtime_fallback_does_not_trigger_for_plain_empty_results():
    primary = _EmptyPrimaryTool()
    fallback = _FallbackTool()
    agent = _build_agent(primary, fallback)
    events = []

    report = agent.research("Industrial agent readiness", progress_cb=events.append)

    assert "# Report" in report
    assert primary.queries == ["Section A latest 90 days 2026", "Section A primary evidence"]
    assert fallback.queries == []
    assert agent.search_meta.provider_effective == "Volcano Engine"
    assert agent.search_meta.fallback_reason == ""
    assert not any(evt["stage"] == "warning" and "runtime provider fallback" in evt["message"].lower() for evt in events)
