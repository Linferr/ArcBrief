"""Summary nodes."""

from typing import List, Dict
from .base import BaseNode
from ..prompts.prompts import SUMMARY_PROMPT, REFLECTION_SUMMARY_PROMPT
from ..utils import parse_json_fallback


class SummaryNode(BaseNode):
    def run(self, title: str, content: str, search_query: str, search_results: List[Dict[str, str]]) -> str:
        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": [item.get("content", "") for item in search_results],
        }
        raw = self.llm.invoke(SUMMARY_PROMPT, str(payload))
        data = parse_json_fallback(raw, {"paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("paragraph_latest_state"):
            return data["paragraph_latest_state"]
        return ""


class ReflectionSummaryNode(BaseNode):
    def run(self, title: str, content: str, search_query: str, search_results: List[Dict[str, str]], latest: str) -> str:
        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": [item.get("content", "") for item in search_results],
            "paragraph_latest_state": latest,
        }
        raw = self.llm.invoke(REFLECTION_SUMMARY_PROMPT, str(payload))
        data = parse_json_fallback(raw, {"updated_paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("updated_paragraph_latest_state"):
            return data["updated_paragraph_latest_state"]
        return latest

