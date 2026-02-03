"""Report structure node."""

from typing import List, Dict
from .base import BaseNode
from ..prompts.prompts import REPORT_STRUCTURE_PROMPT
from ..utils import parse_json_fallback


class ReportStructureNode(BaseNode):
    def run(self, query: str) -> List[Dict[str, str]]:
        raw = self.llm.invoke(REPORT_STRUCTURE_PROMPT, query)
        default = [
            {"title": "Overview", "content": "High-level context and key points."},
            {"title": "Key Developments", "content": "Recent events and updates."},
        ]
        data = parse_json_fallback(raw, default)
        if not isinstance(data, list):
            return default
        cleaned = []
        for item in data:
            if isinstance(item, dict) and item.get("title") and item.get("content"):
                cleaned.append({"title": item["title"], "content": item["content"]})
        return cleaned or default

