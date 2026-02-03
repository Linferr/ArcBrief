"""Host node for academic critique."""

from typing import Dict, List
from .base import BaseNode
from ..prompts.host_prompts import HOST_REFLECT_PROMPT
from ..utils import parse_json_fallback, ensure_list


class HostNode(BaseNode):
    def run(self, title: str, content: str, latest: str) -> Dict[str, List[str]]:
        payload = f"title: {title}\ncontent: {content}\nlatest: {latest}"
        raw = self.llm.invoke(HOST_REFLECT_PROMPT, payload)
        default = {
            "questions": ["What key evidence or statistics are missing?"],
            "suggested_search_queries": [f"{title} evidence statistics"],
            "critique": "Need stronger sources and coverage of counterpoints.",
        }
        data = parse_json_fallback(raw, default)
        if not isinstance(data, dict):
            return default
        return {
            "questions": ensure_list(data.get("questions", default["questions"])),
            "suggested_search_queries": ensure_list(data.get("suggested_search_queries", default["suggested_search_queries"])),
            "critique": data.get("critique", default["critique"]),
        }

