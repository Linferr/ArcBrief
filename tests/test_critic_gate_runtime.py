import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.tools.base import SearchResponse, SearchResult


class _StaticStructureNode:
    def run(self, query, language="English (US)"):
        return [{"title": "Section A", "content": f"Analyze {query}"}]


class _StaticSearchPlanNode:
    def run(self, title, content, language="English (US)", recency_mode="recent_12m_with_90d_anchor"):
        return {"search_queries": [{"query": f"{title} initial official query"}]}


class _TrackingTool:
    def __init__(self):
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        slug = query.lower().replace(" ", "-")
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title=f"Result for {query}",
                    url=f"https://openai.com/{slug}",
                    content=f"Evidence for {query}",
                )
            ],
        )


class _StaticSummaryNode:
    def run(self, title, content, search_query, search_results, language="English (US)"):
        return (
            "Initial summary [S1]",
            {"S1": {"title": "Initial source", "url": "https://openai.com/initial"}},
        )


class _TrackingReflectionSummaryNode:
    def __init__(self):
        self.calls = 0

    def run(self, title, content, search_query, search_results, latest, language="English (US)"):
        self.calls += 1
        return (
            "Updated summary [S1]",
            {"S1": {"title": "Refined source", "url": "https://github.com/example/refined"}},
        )


class _HostSequenceNode:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def run(self, title, content, latest, language="English (US)"):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


class _ForbiddenReflectionNode:
    def run(self, *args, **kwargs):
        raise AssertionError("Reflection node should not be called in this test path")


class _SimpleFormattingNode:
    def __init__(self):
        self.calls = 0

    def run(self, paragraphs, language="English (US)"):
        self.calls += 1
        body = "\n".join(f"## {item['title']}\n{item['content']}" for item in paragraphs)
        return f"# Report\n\n{body}"


class _ForbiddenFormattingNode:
    def run(self, paragraphs, language="English (US)"):
        raise AssertionError("Formatting should not run when critic gate blocks the report")


def _build_agent(host_responses, max_reflections=2):
    settings = Settings(output_dir=os.path.join(ROOT, "_test_outputs"))
    settings.mock_mode = True
    settings.max_reflections = max_reflections
    agent = QueryAgent(settings)
    agent.structure_node = _StaticStructureNode()
    agent.search_node = _StaticSearchPlanNode()
    agent.summary_node = _StaticSummaryNode()
    agent.reflection_summary_node = _TrackingReflectionSummaryNode()
    agent.host_node = _HostSequenceNode(host_responses)
    agent.reflection_node = _ForbiddenReflectionNode()
    agent.formatting_node = _SimpleFormattingNode()
    agent.tool = _TrackingTool()
    return agent


def test_research_pass_gate_skips_reflection_and_emits_gate_event():
    agent = _build_agent(
        [
            {
                "overall_score": 4,
                "gate_decision": "PASS",
                "blocking_issues": [],
                "suggested_queries": [],
                "questions": ["Is this ready?"],
                "critique": "Sufficient evidence.",
                "source_gaps": "",
            }
        ]
    )
    events = []

    report = agent.research("OpenAI latest", progress_cb=events.append)

    assert "## Sources" in report
    assert any(evt["stage"] == "critic_gate" and "PASS" in evt["message"] for evt in events)
    assert agent.last_state.paragraphs[0].reflection_count == 0
    assert len(agent.tool.queries) == 2
    assert all("official release notes" not in query for query in agent.tool.queries)
    assert agent.reflection_summary_node.calls == 0


def test_research_revise_gate_runs_extra_search_then_can_pass():
    agent = _build_agent(
        [
            {
                "overall_score": 2,
                "gate_decision": "REVISE",
                "blocking_issues": ["Need better primary sources."],
                "suggested_queries": ["Section A official release notes"],
                "questions": ["What official note is missing?"],
                "critique": "Need better primary sources.",
                "source_gaps": "Official release notes are missing.",
            },
            {
                "overall_score": 4,
                "gate_decision": "PASS",
                "blocking_issues": [],
                "suggested_queries": [],
                "questions": [],
                "critique": "Coverage is now acceptable.",
                "source_gaps": "",
            },
        ]
    )
    events = []

    report = agent.research("OpenAI latest", progress_cb=events.append)

    gate_messages = [evt["message"] for evt in events if evt["stage"] == "critic_gate"]
    assert any("REVISE" in message for message in gate_messages)
    assert any("PASS" in message for message in gate_messages)
    assert "Refined source" in report
    assert agent.last_state.paragraphs[0].reflection_count == 1
    assert "Section A official release notes" in agent.tool.queries
    assert agent.reflection_summary_node.calls == 1


def test_research_reject_gate_returns_blocked_report_without_formatting():
    agent = _build_agent(
        [
            {
                "overall_score": 1,
                "gate_decision": "REJECT",
                "blocking_issues": ["Timeline claims are unsupported."],
                "suggested_queries": ["OpenAI official release timeline"],
                "questions": ["What official timeline is missing?"],
                "critique": "The current report would mislead the reader.",
                "source_gaps": "No primary source confirms the timeline.",
            }
        ]
    )
    agent.formatting_node = _ForbiddenFormattingNode()
    events = []

    report = agent.research("OpenAI latest", progress_cb=events.append)

    assert "# Research Gate Notice" in report
    assert "Timeline claims are unsupported." in report
    assert any(evt["stage"] == "critic_gate" and "REJECT" in evt["message"] for evt in events)
    assert any(evt["stage"] == "final" and "blocked" in evt["message"].lower() for evt in events)


def test_research_revise_without_budget_returns_blocked_report():
    agent = _build_agent(
        [
            {
                "overall_score": 2,
                "gate_decision": "REVISE",
                "blocking_issues": ["Need stronger corroboration."],
                "suggested_queries": ["OpenAI official corroboration"],
                "questions": ["What corroborates this claim?"],
                "critique": "Corroboration is still weak.",
                "source_gaps": "Only one source currently supports the claim.",
            }
        ],
        max_reflections=0,
    )
    events = []

    report = agent.research("OpenAI latest", progress_cb=events.append)

    assert "# Research Gate Notice" in report
    assert "max reflections" in report.lower()
    assert any(evt["stage"] == "critic_gate" and "REVISE" in evt["message"] for evt in events)
    assert agent.reflection_summary_node.calls == 0
