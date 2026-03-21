import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent import QueryAgent, Settings
from foreign_query_agent.tools.base import SearchResponse, SearchResult


CHATGPT54_QUERY = "\u0063hatgpt5.4\u66f4\u65b0\u7684\u7279\u70b9\u4ee5\u53ca\u4f18\u5316"


class _StaticPremiseNode:
    def run(self, query, language="English (US)"):
        return {
            "premise_status": "invalid",
            "reframed_query": (
                "Verify whether ChatGPT-5.4 is an official OpenAI release. "
                "If not, explain the rumor source and summarize the actual recent OpenAI model updates."
            ),
            "recommended_report_type": "claim_audit",
            "validation_notes": "The named version is not an official OpenAI release.",
            "official_queries": [
                "site:openai.com/blog GPT-5 official announcement",
                "site:platform.openai.com/docs models OpenAI",
            ],
        }


class _ClaimAuditStructureNode:
    def __init__(self):
        self.received_queries = []

    def select_template(self, query: str) -> str:
        return "industry_brief"

    def run_plan(
        self,
        query,
        language="English (US)",
        report_shape="long_analysis",
        length_preset="long",
        report_type=None,
    ):
        self.received_queries.append(query)
        return {
            "report_type": "claim_audit",
            "report_shape": report_shape,
            "length_preset": length_preset,
            "sections": [
                {
                    "title": "Official Status Check",
                    "content": "Verify whether ChatGPT-5.4 exists in official OpenAI channels.",
                    "evidence_type": "official",
                    "target_words": 360,
                    "pass_criteria": "Use at least two official sources.",
                    "subquestions": ["Has OpenAI announced GPT-5 or ChatGPT-5.4?"],
                },
                {
                    "title": "Where The Claim Came From",
                    "content": "Trace community rumor sources and repeated version-number confusion.",
                    "evidence_type": "mixed",
                    "target_words": 340,
                    "pass_criteria": "Identify at least one non-official propagation source.",
                    "subquestions": ["Which community or media sources repeated the claim?"],
                },
                {
                    "title": "What Is Actually True Now",
                    "content": "Summarize the latest real OpenAI model and API updates relevant to the user intent.",
                    "evidence_type": "official",
                    "target_words": 420,
                    "pass_criteria": "Use current official product or API documentation.",
                    "subquestions": ["What is the latest publicly released OpenAI model?"],
                },
                {
                    "title": "Practical Takeaways",
                    "content": "Explain what teams should do instead of planning around a nonexistent version.",
                    "evidence_type": "mixed",
                    "target_words": 320,
                    "pass_criteria": "Translate findings into practical next steps.",
                    "subquestions": ["How should builders evaluate current OpenAI releases?"],
                },
            ],
        }


class _ClaimAuditSearchPlanNode:
    def run(
        self,
        title,
        content,
        language="English (US)",
        recency_mode="recent_12m_with_90d_anchor",
        report_type="industry_brief",
        evidence_type="mixed",
        target_words=None,
        subquestions=None,
    ):
        mapping = {
            "Official Status Check": [
                "site:openai.com/blog GPT-5 official announcement",
                "site:platform.openai.com/docs models OpenAI",
            ],
            "Where The Claim Came From": [
                "\"ChatGPT-5.4\" rumor OR leak OR discussion site:x.com OR site:github.com OR site:reddit.com"
            ],
            "What Is Actually True Now": [
                "site:openai.com/blog GPT-4o launch official",
                "site:platform.openai.com/docs models GPT-4o OpenAI",
            ],
            "Practical Takeaways": [
                "site:openai.com/docs model selection guide OpenAI",
                "site:openai.com/blog OpenAI API updates latest",
            ],
        }
        return {"search_queries": [{"query": item} for item in mapping.get(title, [])]}


class _TrackingTool:
    def __init__(self):
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        lowered = query.lower()
        if "platform.openai.com/docs" in lowered or "site:openai.com" in lowered:
            url = "https://openai.com/blog/gpt-4o"
            title = "OpenAI GPT-4o announcement"
        elif "rumor" in lowered or "site:x.com" in lowered or "site:reddit.com" in lowered:
            url = "https://x.com/example/status/1"
            title = "Community rumor thread"
        else:
            url = "https://platform.openai.com/docs/models"
            title = "OpenAI model documentation"
        return SearchResponse(
            query=query,
            results=[SearchResult(title=title, url=url, content=f"Evidence for {query}")],
        )


class _ClaimAuditSummaryNode:
    def run(
        self,
        title,
        content,
        search_query,
        search_results,
        language="English (US)",
        report_type="industry_brief",
        target_words=None,
        quality_mode="quality_first",
        evidence_type="mixed",
    ):
        content_map = {
            "Official Status Check": "OpenAI has not officially released ChatGPT-5.4 or GPT-5 [S1][S2].",
            "Where The Claim Came From": "The claim appears to come from community rumor and speculative naming reuse [S1].",
            "What Is Actually True Now": "The latest public OpenAI release in the relevant family is GPT-4o, not ChatGPT-5.4 [S1][S2].",
            "Practical Takeaways": "Teams should evaluate current GPT-4o/API capabilities rather than planning around an unreleased version [S1].",
        }
        source_map = {
            f"S{idx}": {
                "title": result["title"],
                "url": result["url"],
                "source_type": "primary" if "openai.com" in result["url"] else "secondary",
            }
            for idx, result in enumerate(search_results, start=1)
        }
        return content_map[title], source_map


class _PassHostNode:
    def run(self, title, content, latest, language="English (US)", report_type="industry_brief", premise_status="valid"):
        return {
            "overall_score": 4,
            "gate_decision": "PASS",
            "blocking_issues": [],
            "questions": [],
            "suggested_queries": [],
            "critique": "Sufficient evidence and correct framing.",
            "source_gaps": "",
        }


class _SimpleFormattingNode:
    def run(
        self,
        paragraphs,
        language="English (US)",
        section_plans=None,
        report_shape="long_analysis",
        report_type="industry_brief",
    ):
        lines = ["# Long-Form Analysis"]
        for item in paragraphs:
            lines.append("")
            lines.append(f"## {item['title']}")
            lines.append(item["content"])
        return "\n".join(lines)


def test_invalid_premise_query_becomes_claim_audit_report():
    settings = Settings(output_dir=os.path.join(ROOT, "_test_outputs"))
    settings.mock_mode = True
    settings.max_reflections = 1
    agent = QueryAgent(settings)
    agent.premise_node = _StaticPremiseNode()
    agent.structure_node = _ClaimAuditStructureNode()
    agent.search_node = _ClaimAuditSearchPlanNode()
    agent.summary_node = _ClaimAuditSummaryNode()
    agent.host_node = _PassHostNode()
    agent.formatting_node = _SimpleFormattingNode()
    agent.tool = _TrackingTool()

    report = agent.research(CHATGPT54_QUERY, language="Chinese (Simplified)")

    assert "# Research Gate Notice" not in report
    assert "## Official Status Check" in report
    assert "## What Is Actually True Now" in report
    assert agent.last_state.spec.premise_status == "invalid"
    assert agent.last_state.spec.effective_query != agent.last_state.spec.original_query
    assert agent.last_state.report_type == "claim_audit"
    assert agent.last_state.report_type_effective == "claim_audit"
    assert agent.last_state.delivery_status == "full"
    assert all("gpt-5-turbo-0318" not in query.lower() for query in agent.tool.queries)
    assert all("chatgpt-5.4 latest 90 days 2026" not in query.lower() for query in agent.tool.queries)
    assert any("site:openai.com/blog" in query.lower() for query in agent.tool.queries)
    assert any("platform.openai.com/docs" in query.lower() for query in agent.tool.queries)
    assert agent.structure_node.received_queries[0] == agent.last_state.spec.effective_query
