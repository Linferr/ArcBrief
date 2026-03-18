"""Report structure node."""

from typing import Dict, List

from .base import BaseNode
from ..prompts.prompts import (
    default_outline_for_template,
    language_instruction,
    report_structure_prompt,
)
from ..utils import parse_json_fallback


PERSON_TEMPLATE_MARKERS = (
    "who is ",
    "profile",
    "biography",
    "leadership",
    "executive",
    "founder",
    "ceo",
    "cto",
    "president",
    "chair",
)

POLICY_TEMPLATE_MARKERS = (
    "policy",
    "regulation",
    "law",
    "bill",
    "act",
    "executive order",
    "compliance",
    "antitrust",
    "governance",
    "regulatory",
    "监管",
    "政策",
    "合规",
)


def select_report_template(query: str) -> str:
    normalized = (query or "").strip().lower()
    if any(marker in normalized for marker in POLICY_TEMPLATE_MARKERS):
        return "policy_analysis"
    if any(marker in normalized for marker in PERSON_TEMPLATE_MARKERS):
        return "person_profile"
    return "industry_brief"


class ReportStructureNode(BaseNode):
    def select_template(self, query: str) -> str:
        return select_report_template(query)

    def run_with_template(
        self,
        query: str,
        template_key: str,
        language: str = "English (US)",
    ) -> List[Dict[str, str]]:
        system_prompt = f"{report_structure_prompt(template_key)}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, query)
        default = default_outline_for_template(template_key)
        data = parse_json_fallback(raw, default)
        if not isinstance(data, list):
            return default
        cleaned = []
        for item in data:
            if isinstance(item, dict) and item.get("title") and item.get("content"):
                cleaned.append({"title": item["title"], "content": item["content"]})
        return cleaned or default

    def run(self, query: str, language: str = "English (US)") -> List[Dict[str, str]]:
        template_key = self.select_template(query)
        return self.run_with_template(query, template_key=template_key, language=language)
