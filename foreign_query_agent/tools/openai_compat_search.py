"""OpenAI-compatible web search adapter for provider SDK unification."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import SearchResponse, SearchResult, as_dict

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


def classify_provider_error(exc: Exception) -> str:
    """Classify a provider exception into a standard error category."""
    s = str(exc).lower()
    if "401" in s or "403" in s or "unauthorized" in s or "authentication" in s:
        return "auth_error"
    if "429" in s or "quota" in s or "rate limit" in s:
        return "quota_error"
    if "400" in s or "missing" in s or "invalid" in s:
        return "request_schema_error"
    if "timeout" in s or "timed out" in s:
        return "timeout"
    return "unknown_error"


class OpenAICompatWebSearchClient:
    """Shared OpenAI-compatible search client used by Zhipu/Volcano providers.

    ``search_mode`` controls how web search is invoked:
    - ``"web_search_tool"`` (Zhipu default): passes ``tools=[{"type": "web_search"}]``
    - ``"plain_chat"`` (Volcano default): omits tools, relies on the model's
      built-in web capabilities via the prompt
    """

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        model: str,
        search_mode: str = "web_search_tool",
    ):
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
        self.search_mode = search_mode
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.last_error_class: str = ""
        self.last_error_message: str = ""

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": f"Search the web and provide references for: {query}"},
                ],
            }
            if self.search_mode == "web_search_tool":
                kwargs["tools"] = [{"type": "web_search"}]

            response = self.client.chat.completions.create(**kwargs)
            payload = as_dict(response)
            items = _extract_candidates(payload)
            results = _map_results(items, max_results=max_results)
            if results:
                self.last_error_class = ""
                self.last_error_message = ""
                return SearchResponse(query=query, results=results)

            text = _extract_message_text(payload).strip()
            if text:
                self.last_error_class = ""
                self.last_error_message = ""
                return SearchResponse(
                    query=query,
                    results=[SearchResult(title=f"{self.provider_name} result for {query}", url="", content=text)],
                )
            self.last_error_class = ""
            self.last_error_message = ""
            return SearchResponse(query=query, results=[])
        except Exception as exc:
            error_class = classify_provider_error(exc)
            self.last_error_class = error_class
            self.last_error_message = str(exc)[:200]
            logger.error(
                "%s search failed [%s]: %s", self.provider_name, error_class, exc,
            )
            return SearchResponse(query=query, results=[])



def _extract_candidates(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    direct_keys = ("citations", "references", "web_results", "search_results", "results")
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend([as_dict(item) for item in value])

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            choice_data = as_dict(choice)
            message = as_dict(choice_data.get("message"))
            for key in direct_keys:
                value = message.get(key)
                if isinstance(value, list):
                    candidates.extend([as_dict(item) for item in value])
            annotations = message.get("annotations")
            if isinstance(annotations, list):
                candidates.extend([as_dict(item) for item in annotations])
    return candidates


def _extract_message_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = as_dict(as_dict(choices[0]).get("message"))
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            item_data = as_dict(item)
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
