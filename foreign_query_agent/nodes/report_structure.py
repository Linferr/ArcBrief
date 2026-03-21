"""Report structure node."""

from typing import Dict, List, Optional

from .base import BaseNode
from ..prompts.prompts import (
    default_outline_for_template,
    default_section_contract,
    language_instruction,
    report_structure_prompt,
    section_word_budget,
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
    "鐩戠",
    "鏀跨瓥",
    "鍚堣",
)

COMPANY_TEMPLATE_MARKERS = (
    "company",
    "business model",
    "competitive position",
    "competition",
    "moat",
    "revenue",
    "pricing",
    "distribution",
    "go to market",
    "go-to-market",
    "startup",
    "firm",
    "vendor",
    "platform",
    "公司",
    "企业",
    "商业模式",
    "营收",
    "竞争",
)

CLAIM_AUDIT_TEMPLATE_MARKERS = (
    "rumor",
    "leak",
    "real or fake",
    "is this real",
    "fact check",
    "fact-check",
    "verify whether",
)


def select_report_template(query: str) -> str:
    normalized = (query or "").strip().lower()
    if any(marker in normalized for marker in CLAIM_AUDIT_TEMPLATE_MARKERS):
        return "claim_audit"
    if any(marker in normalized for marker in POLICY_TEMPLATE_MARKERS):
        return "policy_analysis"
    if any(marker in normalized for marker in PERSON_TEMPLATE_MARKERS):
        return "person_profile"
    if any(marker in normalized for marker in COMPANY_TEMPLATE_MARKERS):
        return "company_analysis"
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
        if isinstance(data, dict):
            data = data.get("sections", default)
        if not isinstance(data, list):
            return default
        cleaned = []
        for item in data:
            if isinstance(item, dict) and item.get("title") and item.get("content"):
                cleaned.append({"title": item["title"], "content": item["content"]})
        return cleaned or default

    def run_plan(
        self,
        query: str,
        language: str = "English (US)",
        report_shape: str = "long_analysis",
        length_preset: str = "long",
        report_type: Optional[str] = None,
    ) -> Dict[str, object]:
        template_key = report_type or self.select_template(query)
        default_sections = default_section_contract(template_key, length_preset=length_preset)
        system_prompt = f"{report_structure_prompt(template_key)}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, query)
        default = {
            "report_type": template_key,
            "sections": default_sections,
        }
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            data = default
        raw_sections = data.get("sections", default_sections)
        sections: List[Dict[str, object]] = []
        if isinstance(raw_sections, list):
            budget = section_word_budget(length_preset, len(raw_sections) or len(default_sections))
            for item in raw_sections:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or "").strip()
                if not title or not content:
                    continue
                sections.append(
                    {
                        "title": title,
                        "content": content,
                        "evidence_type": str(item.get("evidence_type") or "mixed").strip() or "mixed",
                        "target_words": max(220, int(item.get("target_words") or budget)),
                        "pass_criteria": str(
                            item.get("pass_criteria")
                            or "Cite credible evidence, surface contradictions, and avoid unsupported claims."
                        ).strip(),
                        "subquestions": [
                            str(question).strip()
                            for question in (item.get("subquestions") or [])
                            if str(question).strip()
                        ],
                    }
                )
        if not sections:
            sections = default_sections
        return {
            "report_type": template_key,
            "report_shape": report_shape,
            "length_preset": length_preset,
            "sections": sections,
        }

    def run(self, query: str, language: str = "English (US)") -> List[Dict[str, str]]:
        template_key = self.select_template(query)
        return self.run_with_template(query, template_key=template_key, language=language)
