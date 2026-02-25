"""Exa search tool wrapper."""

from __future__ import annotations

import logging
from typing import Any, Dict

from .base import SearchResponse, SearchResult, SearchTool

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

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            response = self.client.search_and_contents(query, num_results=max(1, max_results), text=True)
            payload = _as_dict(response)
            items = payload.get("results", [])
            results = []
            for item in items:
                item_data = _as_dict(item)
                results.append(
                    SearchResult(
                        title=(item_data.get("title") or "").strip(),
                        url=(item_data.get("url") or "").strip(),
                        content=(item_data.get("text") or item_data.get("summary") or "").strip(),
                    )
                )
            return SearchResponse(query=query, results=[r for r in results if r.title or r.url or r.content])
        except Exception as exc:
            logger.warning("Exa search failed: %s", exc)
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
