import os
import sys
import threading
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.tools.base import SearchResponse, SearchResult


class _ThreeSectionStructureNode:
    def run(self, query, language="English (US)"):
        return [
            {"title": "Section A", "content": f"Analyze A for {query}"},
            {"title": "Section B", "content": f"Analyze B for {query}"},
            {"title": "Section C", "content": f"Analyze C for {query}"},
        ]


class _SingleQuerySearchPlanNode:
    def run(self, title, content, language="English (US)", recency_mode="recent_12m_with_90d_anchor"):
        return {"search_queries": [{"query": f"{title} primary evidence"}]}


class _ConcurrentTool:
    def __init__(self, failing_queries=None):
        self.failing_queries = set(failing_queries or [])
        self._lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0

    def search(self, query, max_results=5):
        with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            time.sleep(0.05)
            if query in self.failing_queries:
                raise RuntimeError(f"provider timeout for {query}")
            slug = query.lower().replace(" ", "-")
            return SearchResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"Result for {query}",
                        url=f"https://example.com/{slug}",
                        content=f"Evidence for {query}",
                    )
                ],
            )
        finally:
            with self._lock:
                self.inflight -= 1


class _SimpleSummaryNode:
    def run(self, title, content, search_query, search_results, language="English (US)"):
        return (
            f"{title} summary [S1]",
            {"S1": {"title": f"{title} source", "url": f"https://example.com/{title.lower().replace(' ', '-')}"}},
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


def _build_agent(failing_queries=None):
    settings = Settings(output_dir=os.path.join(ROOT, "_test_outputs"))
    settings.mock_mode = True
    settings.max_parallel_sections = 3
    settings.max_reflections = 1
    agent = QueryAgent(settings)
    agent.structure_node = _ThreeSectionStructureNode()
    agent.search_node = _SingleQuerySearchPlanNode()
    agent.summary_node = _SimpleSummaryNode()
    agent.host_node = _HostPassNode()
    agent.formatting_node = _EchoFormattingNode()
    agent.tool = _ConcurrentTool(failing_queries=failing_queries)
    return agent


def test_parallel_runtime_processes_multiple_sections_concurrently():
    agent = _build_agent()

    report = agent.research("Industrial agent readiness")

    assert "## Section A" in report
    assert "## Section B" in report
    assert "## Section C" in report
    assert agent.tool.max_inflight > 1


def test_parallel_runtime_falls_back_for_failed_section_without_aborting_report():
    agent = _build_agent(failing_queries={"Section B primary evidence"})
    events = []

    report = agent.research("Industrial agent readiness", progress_cb=events.append)

    assert "## Section A" in report
    assert "## Section C" in report
    assert "Evidence insufficient for this section." in report
    assert "Fallback reason:" in report
    assert any(evt["stage"] == "error" and "Section fallback" in evt["message"] for evt in events)
