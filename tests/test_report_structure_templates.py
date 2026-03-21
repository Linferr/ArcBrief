import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent.nodes.report_structure import ReportStructureNode, select_report_template
from foreign_query_agent.prompts.prompts import default_outline_for_template


CHATGPT54_QUERY = "\u0063hatgpt5.4\u66f4\u65b0\u7684\u7279\u70b9\u4ee5\u53ca\u4f18\u5316"


class _JsonlessLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(system_prompt)
        return "{}"


def test_select_report_template_variants():
    assert select_report_template("US AI policy compliance update") == "policy_analysis"
    assert select_report_template("Sam Altman leadership profile and influence") == "person_profile"
    assert select_report_template("Anthropic company business model and moat") == "company_analysis"
    assert select_report_template("Open source coding agents market update") == "industry_brief"


def test_report_structure_node_uses_policy_template_defaults_when_llm_fails():
    llm = _JsonlessLLM()
    node = ReportStructureNode(llm)

    outline = node.run("US AI policy compliance update", language="English (US)")

    assert outline == default_outline_for_template("policy_analysis")
    assert "Template mode: policy_analysis" in llm.prompts[0]


def test_report_structure_node_uses_person_template_defaults_when_llm_fails():
    llm = _JsonlessLLM()
    node = ReportStructureNode(llm)

    outline = node.run("Who is Sam Altman profile", language="English (US)")

    assert outline == default_outline_for_template("person_profile")
    assert "Template mode: person_profile" in llm.prompts[0]


def test_report_structure_node_returns_company_section_contract_when_llm_fails():
    llm = _JsonlessLLM()
    node = ReportStructureNode(llm)

    plan = node.run_plan(
        "Anthropic company business model and moat",
        language="English (US)",
        report_shape="long_analysis",
        length_preset="long",
    )

    assert plan["report_type"] == "company_analysis"
    assert plan["report_shape"] == "long_analysis"
    assert plan["length_preset"] == "long"
    assert len(plan["sections"]) == 4
    assert all(section["title"] for section in plan["sections"])
    assert all(section["target_words"] >= 220 for section in plan["sections"])
    assert all(section["evidence_type"] for section in plan["sections"])
    assert "Template mode: company_analysis" in llm.prompts[0]


def test_report_structure_node_returns_claim_audit_contract_when_forced():
    llm = _JsonlessLLM()
    node = ReportStructureNode(llm)

    plan = node.run_plan(
        CHATGPT54_QUERY,
        language="Chinese (Simplified)",
        report_shape="long_analysis",
        length_preset="long",
        report_type="claim_audit",
    )

    assert plan["report_type"] == "claim_audit"
    titles = [section["title"] for section in plan["sections"]]
    assert titles == [
        "Official Status Check",
        "Where The Claim Came From",
        "What Is Actually True Now",
        "Practical Takeaways",
    ]
    assert all(300 <= int(section["target_words"]) <= 550 for section in plan["sections"])
    assert "Template mode: claim_audit" in llm.prompts[0]
