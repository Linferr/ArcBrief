"""Exa search tool wrapper."""

from __future__ import annotations

import logging

from .base import SearchResponse, SearchResult, SearchTool, as_dict
from .openai_compat_search import classify_provider_error

logger = logging.getLogger(__name__)

try:
    from exa_py import Exa
except Exception:  # pragma: no cover - optional dependency
    Exa = None


class ExaSearchTool(SearchTool):
    """Exa API client wrapper."""

    def __init__(self, api_key: str):
        if Exa is None:
            raise RuntimeError("exa-py package is not installed.")
        if not api_key:
            raise ValueError("Exa API key is required.")
        self.client = Exa(api_key=api_key)
        self.search_mode = "search_api"
        self.last_error_class = ""
        self.last_error_message = ""

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            response = self.client.search_and_contents(query, num_results=max(1, max_results), text=True)
            payload = as_dict(response)
            items = payload.get("results", [])
            results = []
            for item in items:
                item_data = as_dict(item)
                results.append(
                    SearchResult(
                        title=(item_data.get("title") or "").strip(),
                        url=(item_data.get("url") or "").strip(),
                        content=(item_data.get("text") or item_data.get("summary") or "").strip(),
                    )
                )
            self.last_error_class = ""
            self.last_error_message = ""
            return SearchResponse(query=query, results=[r for r in results if r.title or r.url or r.content])
        except Exception as exc:
            error_class = classify_provider_error(exc)
            logger.error("Exa search failed [%s]: %s", error_class, exc)
            self.last_error_class = error_class
            self.last_error_message = str(exc)[:200]
            return SearchResponse(query=query, results=[])
