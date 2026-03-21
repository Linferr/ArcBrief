"""Premise validation node."""

import re
from typing import Any, Dict, List

from .base import BaseNode
from ..prompts.prompts import PREMISE_CHECK_PROMPT, language_instruction
from ..state import PremiseCheckResult
from ..utils import parse_json_fallback


_INVALID_OPENAI_VERSION_PATTERNS = (
    "chatgpt5.4",
    "chatgpt-5.4",
    "gpt5.4",
    "gpt-5.4",
    "gpt-5-turbo-0318",
)

_DISPUTED_MARKERS = (
    "is this real",
    "real or fake",
    "rumor",
    "leak",
    "unconfirmed",
)


class PremiseCheckNode(BaseNode):
    def _heuristic_result(self, query: str) -> PremiseCheckResult:
        normalized = re.sub(r"\s+", "", (query or "").strip().lower())
        if any(marker in normalized for marker in _INVALID_OPENAI_VERSION_PATTERNS):
            return PremiseCheckResult(
                premise_status="invalid",
                reframed_query=(
                    "Verify whether ChatGPT-5.4 is an official OpenAI release. "
                    "If it is not real, explain where the claim came from and summarize the actual recent OpenAI model updates."
                ),
                recommended_report_type="claim_audit",
                validation_notes="The query appears to reference a likely non-official OpenAI model/version label.",
                official_queries=[
                    "site:openai.com/blog GPT-5 official announcement",
                    "site:platform.openai.com/docs models OpenAI",
                    "site:openai.com API model changelog OpenAI",
                ],
            )
        if any(marker in (query or "").lower() for marker in _DISPUTED_MARKERS):
            return PremiseCheckResult(
                premise_status="disputed",
                reframed_query=(query or "").strip(),
                recommended_report_type="claim_audit",
                validation_notes="The query includes rumor or verification language and should be checked first.",
                official_queries=[],
            )
        return PremiseCheckResult(
            premise_status="valid",
            reframed_query=(query or "").strip(),
            recommended_report_type="",
            validation_notes="",
            official_queries=[],
        )

    def run(self, query: str, language: str = "English (US)") -> Dict[str, Any]:
        fallback = self._heuristic_result(query)
        system_prompt = f"{PREMISE_CHECK_PROMPT}\n{language_instruction(language)}"
        try:
            raw = self.llm.invoke(system_prompt, query)
        except Exception:
            return fallback.to_dict()

        data = parse_json_fallback(raw, {})
        if not isinstance(data, dict) or not data:
            return fallback.to_dict()

        premise_status = str(data.get("premise_status") or fallback.premise_status).strip().lower()
        if premise_status not in {"valid", "disputed", "invalid"}:
            premise_status = fallback.premise_status

        reframed_query = str(data.get("reframed_query") or fallback.reframed_query or query).strip()
        recommended_report_type = str(
            data.get("recommended_report_type") or fallback.recommended_report_type
        ).strip()
        validation_notes = str(data.get("validation_notes") or fallback.validation_notes).strip()

        official_queries: List[str] = []
        raw_queries = data.get("official_queries")
        if isinstance(raw_queries, list):
            for item in raw_queries:
                text = str(item or "").strip()
                if text and text not in official_queries:
                    official_queries.append(text)
        if not official_queries:
            official_queries = list(fallback.official_queries)

        if premise_status in {"invalid", "disputed"} and not recommended_report_type:
            recommended_report_type = "claim_audit"
        if not reframed_query:
            reframed_query = fallback.reframed_query or (query or "").strip()

        return PremiseCheckResult(
            premise_status=premise_status,
            reframed_query=reframed_query,
            recommended_report_type=recommended_report_type,
            validation_notes=validation_notes,
            official_queries=official_queries,
        ).to_dict()
