"""Deep Research actionable output tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.nodes.formatting import FormattingNode
from foreign_query_agent.nodes.summary import SummaryNode


class _PlainLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "Short draft without sections."


class _EmptyJsonLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "{}"


def test_formatting_enforces_required_sections():
    node = FormattingNode(_PlainLLM())
    report = node.run([{"title": "t", "content": "c"}], language="English (US)")
    assert "## Latest Viewpoints" in report
    assert "## Actionable Tactics" in report
    assert "## Toolchain and Config Templates" in report
    assert "## Risks & Contrarian Views" in report
    # Sources is NOT in _required_sections — it is appended by agent._append_sources()
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
