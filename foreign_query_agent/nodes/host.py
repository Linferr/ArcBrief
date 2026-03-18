"""Host node for academic critique."""

from typing import Any, Dict

from .base import BaseNode
from ..prompts.host_prompts import HOST_REFLECT_PROMPT
from ..prompts.prompts import language_instruction
from ..state import CriticResult
from ..utils import parse_json_fallback


class HostNode(BaseNode):
    def run(self, title: str, content: str, latest: str, language: str = "English (US)") -> Dict[str, Any]:
        payload = f"title: {title}\ncontent: {content}\nlatest: {latest}"
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
        return CriticResult.from_payload(
            data,
            fallback_query=f"{title} evidence statistics",
        ).to_dict()
