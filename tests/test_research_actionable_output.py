"""Deep Research actionable output tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.nodes.formatting import FormattingNode
from foreign_query_agent.nodes.summary import SummaryNode
from foreign_query_agent.state import SectionPlan


class _PlainLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "Short draft without sections."


class _EmptyJsonLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "{}"


def test_formatting_uses_planned_sections_instead_of_fixed_defaults():
    node = FormattingNode(_PlainLLM())
    plans = [
        SectionPlan(title="Strategic Context", content="Why it matters now.", evidence_type="market", target_words=260),
        SectionPlan(title="Competitive Position", content="How the company is positioned.", evidence_type="primary", target_words=300),
        SectionPlan(title="Execution Risks", content="Where the thesis may break.", evidence_type="contrarian", target_words=240),
    ]
    report = node.run(
        [{"title": "t", "content": "c"}],
        language="English (US)",
        section_plans=plans,
        report_shape="long_analysis",
        report_type="company_analysis",
    )
    assert "## Strategic Context" in report
    assert "## Competitive Position" in report
    assert "## Execution Risks" in report
    assert "## Latest Viewpoints" not in report
    assert "## Sources" not in report


def test_summary_returns_evidence_insufficient_message_when_llm_output_invalid():
    node = SummaryNode(_EmptyJsonLLM())
    text, source_map = node.run(
        "Karpathy practical workflow",
        "Need practical tactics.",
        "karpathy workflow latest",
        [{"title": "post", "url": "https://x.com/a", "content": "example content"}],
        language="English (US)",
    )
    assert "Evidence" in text
    assert "[S1]" in text
    assert "S1" in source_map
    assert source_map["S1"]["url"] == "https://x.com/a"
