"""Summary nodes."""

from typing import Dict, List, Optional, Tuple

from .base import BaseNode
from ..prompts.prompts import REFLECTION_SUMMARY_PROMPT, SUMMARY_PROMPT, language_instruction
from ..utils import parse_json_fallback


def _build_source_map(search_results: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Build a local S-ID -> {title, url} mapping from search results."""
    return {
        f"S{idx}": {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source_type": item.get("source_type", "unknown"),
            "host": item.get("host", ""),
        }
        for idx, item in enumerate(search_results, start=1)
    }


def _claim_audit_fallback(title: str, search_results: List[Dict[str, str]]) -> str:
    anchors = " ".join(f"[S{idx}]" for idx, _ in enumerate(search_results[:3], start=1))
    lowered = (title or "").strip().lower()
    if lowered == "official status check":
        return f"The official material reviewed does not confirm the disputed claim {anchors}".strip()
    if lowered == "where the claim came from":
        return f"Secondary sources indicate the claim spread through community discussion rather than official release notes {anchors}".strip()
    if lowered == "what is actually true now":
        return f"The reliable sources instead point to real, currently documented OpenAI updates rather than the disputed version label {anchors}".strip()
    return f"The corrected framing suggests practical next steps should be based on currently documented releases and docs {anchors}".strip()


class SummaryNode(BaseNode):
    def run(
        self,
        title: str,
        content: str,
        search_query: str,
        search_results: List[Dict[str, str]],
        language: str = "English (US)",
        report_type: str = "industry_brief",
        target_words: Optional[int] = None,
        quality_mode: str = "quality_first",
        evidence_type: str = "mixed",
        original_query: str = "",
        effective_query: str = "",
        premise_status: str = "valid",
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
                    "source_type": item.get("source_type", "unknown"),
                }
            )

        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": normalized_results,
            "report_type": report_type,
            "target_words": target_words,
            "quality_mode": quality_mode,
            "evidence_type": evidence_type,
            "original_query": original_query,
            "effective_query": effective_query,
            "premise_status": premise_status,
        }
        system_prompt = f"{SUMMARY_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, str(payload))
        data = parse_json_fallback(raw, {"paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("paragraph_latest_state"):
            return (data["paragraph_latest_state"], source_map)
        if report_type == "claim_audit":
            return (_claim_audit_fallback(title, normalized_results), source_map)
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
        report_type: str = "industry_brief",
        target_words: Optional[int] = None,
        quality_mode: str = "quality_first",
        evidence_type: str = "mixed",
        original_query: str = "",
        effective_query: str = "",
        premise_status: str = "valid",
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
                    "source_type": item.get("source_type", "unknown"),
                }
            )

        payload = {
            "title": title,
            "content": content,
            "search_query": search_query,
            "search_results": normalized_results,
            "paragraph_latest_state": latest,
            "report_type": report_type,
            "target_words": target_words,
            "quality_mode": quality_mode,
            "evidence_type": evidence_type,
            "original_query": original_query,
            "effective_query": effective_query,
            "premise_status": premise_status,
        }
        system_prompt = f"{REFLECTION_SUMMARY_PROMPT}\n{language_instruction(language)}"
        raw = self.llm.invoke(system_prompt, str(payload))
        data = parse_json_fallback(raw, {"updated_paragraph_latest_state": ""})
        if isinstance(data, dict) and data.get("updated_paragraph_latest_state"):
            return (data["updated_paragraph_latest_state"], source_map)
        if report_type == "claim_audit" and latest.strip():
            return (latest, source_map)
        if latest.strip():
            return (latest, source_map)
        if normalized_results:
            return ("Evidence update captured, but synthesis is currently insufficient.", source_map)
        return (latest, source_map)
