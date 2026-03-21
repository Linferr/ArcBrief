"""Host node for academic critique."""

import re
from typing import Any, Dict

from .base import BaseNode
from ..prompts.host_prompts import HOST_REFLECT_PROMPT
from ..prompts.prompts import language_instruction
from ..state import CriticResult
from ..utils import parse_json_fallback


class HostNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        latest: str,
        language: str = "English (US)",
        report_type: str = "industry_brief",
        premise_status: str = "valid",
    ) -> Dict[str, Any]:
        payload = (
            f"title: {title}\n"
            f"content: {content}\n"
            f"latest: {latest}\n"
            f"report_type: {report_type}\n"
            f"premise_status: {premise_status}"
        )
        system_prompt = f"{HOST_REFLECT_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, payload)
        default = {
            "overall_score": 2,
            "gate_decision": "REVISE",
            "blocking_issues": ["Need stronger sources and coverage of counterpoints."],
            "questions": ["What key evidence or statistics are missing?"],
            "suggested_search_queries": [f"{title} evidence statistics"],
            "critique": "Need stronger sources and coverage of counterpoints.",
            "source_gaps": "Primary source coverage is weak.",
        }
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            data = default
        result = CriticResult.from_payload(
            data,
            fallback_query=f"{title} evidence statistics",
        )
        if self._should_auto_pass_claim_audit(latest, report_type=report_type, premise_status=premise_status):
            result.gate_decision = "PASS"
            result.overall_score = max(result.overall_score, 4)
            result.blocking_issues = []
        return result.to_dict()

    @staticmethod
    def _should_auto_pass_claim_audit(latest: str, *, report_type: str, premise_status: str) -> bool:
        if report_type != "claim_audit" or premise_status not in {"invalid", "disputed"}:
            return False
        lowered = (latest or "").lower()
        source_anchor_count = len(set(re.findall(r"\[s(\d+)\]", lowered)))
        correction_markers = (
            "not officially released",
            "not an official",
            "does not officially exist",
            "has not officially released",
            "not real",
            "rumor",
        )
        return source_anchor_count >= 2 and any(marker in lowered for marker in correction_markers)
