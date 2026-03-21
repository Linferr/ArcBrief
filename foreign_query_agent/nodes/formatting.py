"""Formatting node."""

from typing import Dict, List, Optional

from .base import BaseNode
from ..prompts.prompts import FORMAT_PROMPT, language_instruction
from ..state import SectionPlan


def _normalize_section_plans(section_plans: Optional[List[SectionPlan | Dict[str, object]]]) -> List[Dict[str, object]]:
    normalized: List[Dict[str, object]] = []
    for item in section_plans or []:
        if isinstance(item, SectionPlan):
            normalized.append(item.to_dict())
        elif isinstance(item, dict) and item.get("title"):
            normalized.append(dict(item))
    return normalized


def _ensure_planned_sections(
    report: str,
    section_plans: List[Dict[str, object]],
    report_shape: str,
) -> str:
    text = (report or "").strip()
    if not text.startswith("#"):
        heading = "# Long-Form Analysis" if report_shape == "long_analysis" else "# Report"
        text = f"{heading}\n\n{text}".strip()

    existing_h2 = [line.strip() for line in text.splitlines() if line.strip().startswith("## ")]
    if len(existing_h2) >= len(section_plans) and section_plans:
        return text

    for section in section_plans:
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        found = any(title.lower() in header.lower() for header in existing_h2)
        if not found:
            text += "\n\n" + f"## {title}\n- Evidence insufficient."
    return text.strip()


class FormattingNode(BaseNode):
    def run(
        self,
        paragraphs: List[Dict[str, str]],
        language: str = "English (US)",
        section_plans: Optional[List[SectionPlan | Dict[str, object]]] = None,
        report_shape: str = "long_analysis",
        report_type: str = "industry_brief",
    ) -> str:
        normalized_plans = _normalize_section_plans(section_plans)
        payload = {
            "report_type": report_type,
            "report_shape": report_shape,
            "section_contract": normalized_plans,
            "sections": paragraphs,
        }
        system_prompt = f"{FORMAT_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, str(payload))
        return _ensure_planned_sections(raw, normalized_plans, report_shape)
