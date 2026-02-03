"""Search planning node."""

from typing import Dict
from .base import BaseNode
from ..prompts.prompts import FIRST_SEARCH_PROMPT
from ..utils import parse_json_fallback


class SearchPlanNode(BaseNode):
    def run(self, title: str, content: str) -> Dict[str, str]:
        payload = f"title: {title}\ncontent: {content}"
        raw = self.llm.invoke(FIRST_SEARCH_PROMPT, payload)
        default = {"search_query": f"{title} latest", "search_tool": "basic_search", "reasoning": "default"}
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            return default
        return {
            "search_query": data.get("search_query", default["search_query"]),
            "search_tool": data.get("search_tool", "basic_search"),
            "reasoning": data.get("reasoning", "")
        }

