import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_query_agent.nodes.host import HostNode
from foreign_query_agent.prompts.host_prompts import HOST_REFLECT_PROMPT


class _StaticLLM:
    def __init__(self, payload: str):
        self.payload = payload

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return self.payload


def test_host_node_returns_structured_critic_result_fields():
    llm = _StaticLLM(
        """
        {
          "overall_score": 4,
          "gate_decision": "PASS",
          "blocking_issues": [],
          "questions": ["Is the sourcing sufficiently recent?"],
          "suggested_queries": ["OpenAI official announcement March 2026"],
          "critique": "Coverage is acceptable after cross-verification.",
          "source_gaps": "No material source gap detected."
        }
        """
    )
    node = HostNode(llm)

    result = node.run("OpenAI update", "Need latest verified changes.", "Summary here.")

    assert result["overall_score"] == 4
    assert result["gate_decision"] == "PASS"
    assert result["blocking_issues"] == []
    assert result["questions"] == ["Is the sourcing sufficiently recent?"]
    assert result["suggested_queries"] == ["OpenAI official announcement March 2026"]
    assert result["suggested_search_queries"] == ["OpenAI official announcement March 2026"]
    assert result["critique"] == "Coverage is acceptable after cross-verification."
    assert result["source_gaps"] == "No material source gap detected."


def test_host_node_normalizes_missing_or_invalid_gate_fields_to_revise():
    llm = _StaticLLM(
        """
        {
          "overall_score": 9,
          "gate_decision": "ship_it",
          "questions": "What primary sources are still missing?",
          "suggested_search_queries": "Anthropic official safety report",
          "critique": "Primary source coverage is still weak."
        }
        """
    )
    node = HostNode(llm)

    result = node.run("Anthropic update", "Need stronger sourcing.", "Current summary.")

    assert result["overall_score"] == 5
    assert result["gate_decision"] == "REVISE"
    assert result["questions"] == ["What primary sources are still missing?"]
    assert result["suggested_queries"] == ["Anthropic official safety report"]
    assert result["suggested_search_queries"] == ["Anthropic official safety report"]
    assert result["blocking_issues"] == ["Primary source coverage is still weak."]


def test_host_prompt_requests_gate_schema_fields():
    assert "gate_decision" in HOST_REFLECT_PROMPT
    assert "overall_score" in HOST_REFLECT_PROMPT
    assert "blocking_issues" in HOST_REFLECT_PROMPT
    assert "PASS|REVISE|REJECT" in HOST_REFLECT_PROMPT
