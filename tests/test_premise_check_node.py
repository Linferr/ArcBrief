import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent.nodes.premise_check import PremiseCheckNode


CHATGPT54_QUERY = "\u0063hatgpt5.4\u66f4\u65b0\u7684\u7279\u70b9\u4ee5\u53ca\u4f18\u5316"


class _JsonlessLLM:
    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return "{}"


def test_premise_check_marks_chatgpt54_query_invalid_and_reframes():
    node = PremiseCheckNode(_JsonlessLLM())

    result = node.run(CHATGPT54_QUERY, language="Chinese (Simplified)")

    assert result["premise_status"] == "invalid"
    assert result["recommended_report_type"] == "claim_audit"
    assert result["reframed_query"] != CHATGPT54_QUERY
    assert "OpenAI" in result["reframed_query"]
    assert len(result["official_queries"]) >= 2


def test_premise_check_leaves_normal_query_valid():
    node = PremiseCheckNode(_JsonlessLLM())

    result = node.run("Anthropic company business model and moat", language="English (US)")

    assert result["premise_status"] == "valid"
    assert result["recommended_report_type"] in {"", "industry_brief", "company_analysis"}
    assert result["reframed_query"] == "Anthropic company business model and moat"
