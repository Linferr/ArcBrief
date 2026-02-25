"""Search planning node."""

from datetime import datetime
from typing import Dict

from .base import BaseNode
from ..prompts.prompts import FIRST_SEARCH_PROMPT, language_instruction, recency_instruction
from ..utils import parse_json_fallback


class SearchPlanNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        language: str = "English (US)",
        recency_mode: str = "recent_12m_with_90d_anchor",
    ) -> Dict[str, object]:
        payload = f"title: {title}\ncontent: {content}"
        system_prompt = (
            f"{FIRST_SEARCH_PROMPT}\n"
            f"{language_instruction(language)}\n"
            f"{recency_instruction(recency_mode)}"
        )
        raw = self.llm.invoke(system_prompt, payload)
        current_year = datetime.utcnow().year
        default = {
            "search_queries": [
                {
                    "intent": "latest_viewpoints",
                    "query": f"{title} latest 90 days {current_year} Vibe Coding Agentic Engineering RLVR Claws",
                },
                {
                    "intent": "actionable_tactics",
                    "query": f"{title} workflow template tools rules file .cursorrules CLAUDE.md",
                },
                {
                    "intent": "risks_counterpoints",
                    "query": f"{title} risks limitations critique skill erosion slopacolypse",
                },
            ],
            "search_query": f"{title} latest {current_year}",
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