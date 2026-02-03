"""Reflection node."""

from typing import Dict
from .base import BaseNode
from ..prompts.prompts import REFLECTION_PROMPT
from ..utils import parse_json_fallback


class ReflectionNode(BaseNode):
    def run(self, title: str, content: str, latest: str) -> Dict[str, str]:
        payload = f"title: {title}\ncontent: {content}\nlatest: {latest}"
        raw = self.llm.invoke(REFLECTION_PROMPT, payload)
        default = {"search_query": f"{title} background", "search_tool": "basic_search", "reasoning": "default"}
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            return default
        return {
            "search_query": data.get("search_query", default["search_query"]),
            "search_tool": data.get("search_tool", "basic_search"),
            "reasoning": data.get("reasoning", "")
        }

