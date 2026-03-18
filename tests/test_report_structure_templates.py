import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from foreign_query_agent.nodes.report_structure import ReportStructureNode, select_report_template
from foreign_query_agent.prompts.prompts import default_outline_for_template


class _JsonlessLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(system_prompt)
        return "{}"


def test_select_report_template_variants():
    assert select_report_template("US AI policy compliance update") == "policy_analysis"
    assert select_report_template("Sam Altman leadership profile and influence") == "person_profile"
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
