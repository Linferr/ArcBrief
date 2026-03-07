"""Summary nodes."""

from typing import Dict, List, Tuple

from .base import BaseNode
from ..prompts.prompts import REFLECTION_SUMMARY_PROMPT, SUMMARY_PROMPT, language_instruction
from ..utils import parse_json_fallback


def _build_source_map(search_results: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Build a local S-ID -> {title, url} mapping from search results."""
    return {
        f"S{idx}": {"title": item.get("title", ""), "url": item.get("url", "")}
        for idx, item in enumerate(search_results, start=1)
    }


class SummaryNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        search_query: str,
        search_results: List[Dict[str, str]],
        language: str = "English (US)",
    ) -> Tuple[str, Dict[str, Dict[str, str]]]:
        source_map = _build_source_map(search_results)

        if not search_results:
            return ("Evidence insufficient for this section — no search results available.", {})

        normalized_results = []
        for idx, item in enumerate(search_results, start=1):
            normalized_results.append(
                {
                    "id": f"S{idx}",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
            )

        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": normalized_results,
        }
        system_prompt = f"{SUMMARY_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, str(payload))
        data = parse_json_fallback(raw, {"paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("paragraph_latest_state"):
            return (data["paragraph_latest_state"], source_map)
        if normalized_results:
            return ("Evidence collected but synthesis failed. Refer to [S1] for baseline evidence.", source_map)
        return ("", {})


class ReflectionSummaryNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        search_query: str,
        search_results: List[Dict[str, str]],
        latest: str,
        language: str = "English (US)",
    ) -> Tuple[str, Dict[str, Dict[str, str]]]:
        source_map = _build_source_map(search_results)

        if not search_results:
            return (latest or "Evidence insufficient for this section.", source_map)

        normalized_results = []
        for idx, item in enumerate(search_results, start=1):
            normalized_results.append(
                {
                    "id": f"S{idx}",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
            )

        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": normalized_results,
            "paragraph_latest_state": latest,
        }
        system_prompt = f"{REFLECTION_SUMMARY_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, str(payload))
        data = parse_json_fallback(raw, {"updated_paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("updated_paragraph_latest_state"):
            return (data["updated_paragraph_latest_state"], source_map)
        if latest.strip():
            return (latest, source_map)
        if normalized_results:
            return ("Evidence update captured, but synthesis is currently insufficient.", source_map)
        return (latest, source_map)
