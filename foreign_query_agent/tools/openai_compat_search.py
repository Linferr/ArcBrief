"""OpenAI-compatible web search adapter for provider SDK unification."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import SearchResponse, SearchResult

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


class OpenAICompatWebSearchClient:
    """Shared OpenAI-compatible search client used by Zhipu/Volcano providers."""

    def __init__(self, *, provider_name: str, api_key: str, base_url: str, model: str):
        if OpenAI is None:
            raise RuntimeError("openai package is not installed.")
        if not api_key:
            raise ValueError(f"{provider_name} API key is required.")
        if not base_url:
            raise ValueError(f"{provider_name} base URL is required.")
        if not model:
            raise ValueError(f"{provider_name} model is required.")
        self.provider_name = provider_name
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": f"Search the web and provide references for: {query}"}],
                tools=[{"type": "web_search"}],
            )
            payload = _as_dict(response)
            items = _extract_candidates(payload)
            results = _map_results(items, max_results=max_results)
            if results:
                return SearchResponse(query=query, results=results)

            text = _extract_message_text(payload).strip()
            if text:
                return SearchResponse(
                    query=query,
                    results=[SearchResult(title=f"{self.provider_name} result for {query}", url="", content=text)],
                )
            return SearchResponse(query=query, results=[])
        except Exception as exc:
            logger.warning("%s OpenAI-compatible search failed: %s", self.provider_name, exc)
            return SearchResponse(query=query, results=[])


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    data = getattr(value, "__dict__", None)
    return data if isinstance(data, dict) else {}


def _extract_candidates(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    direct_keys = ("citations", "references", "web_results", "search_results", "results")
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend([_as_dict(item) for item in value])

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            choice_data = _as_dict(choice)
            message = _as_dict(choice_data.get("message"))
            for key in direct_keys:
                value = message.get(key)
                if isinstance(value, list):
                    candidates.extend([_as_dict(item) for item in value])
            annotations = message.get("annotations")
            if isinstance(annotations, list):
                candidates.extend([_as_dict(item) for item in annotations])
    return candidates


def _extract_message_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = _as_dict(_as_dict(choices[0]).get("message"))
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            item_data = _as_dict(item)
            text = item_data.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    return ""


def _map_results(items: List[Dict[str, Any]], max_results: int) -> List[SearchResult]:
    results: List[SearchResult] = []
    for item in items:
        title = (
            item.get("title")
            or item.get("name")
            or item.get("source_title")
            or item.get("site_name")
            or ""
        ).strip()
        url = (item.get("url") or item.get("link") or item.get("source_url") or "").strip()
        content = (item.get("content") or item.get("snippet") or item.get("summary") or "").strip()
        if title or url or content:
            results.append(SearchResult(title=title, url=url, content=content))
        if len(results) >= max(1, max_results):
            break
    return results
