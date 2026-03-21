"""Reflection node."""

from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseNode
from ..prompts.prompts import REFLECTION_PROMPT, language_instruction, recency_instruction
from ..utils import parse_json_fallback


class ReflectionNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        latest: str,
        language: str = "English (US)",
        recency_mode: str = "recent_12m_with_90d_anchor",
        report_type: str = "industry_brief",
        evidence_type: str = "mixed",
        target_words: Optional[int] = None,
        subquestions: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        payload = str(
            {
                "title": title,
                "content": content,
                "latest": latest,
                "report_type": report_type,
                "evidence_type": evidence_type,
                "target_words": target_words,
                "subquestions": subquestions or [],
            }
        )
        system_prompt = (
            f"{REFLECTION_PROMPT}\n"
            f"{language_instruction(language)}\n"
            f"{recency_instruction(recency_mode)}"
        )
        raw = self.llm.invoke(system_prompt, payload)
        current_year = datetime.utcnow().year
        default = {
            "search_queries": [
                {"intent": "latest_gap", "query": f"{title} latest 90 days {current_year}"},
                {"intent": "source_gap", "query": f"{title} official source interview filing transcript"},
                {"intent": "actionability_gap", "query": f"{title} implementation detail workflow template config"},
            ],
            "search_query": f"{title} background",
            "search_tool": "basic_search",
            "reasoning": "default",
        }
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            return default
        return {
            "search_queries": data.get("search_queries", default["search_queries"]),
            "search_query": data.get("search_query", default["search_query"]),
            "search_tool": data.get("search_tool", "basic_search"),
            "reasoning": data.get("reasoning", ""),
        }
