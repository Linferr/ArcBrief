"""Bocha web search tool wrapper."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

import requests

from .base import SearchResponse, SearchResult, SearchTool
from .openai_compat_search import classify_provider_error

logger = logging.getLogger(__name__)


class BochaSearchTool(SearchTool):
    """Bocha HTTP API client."""

    ENDPOINT = "https://api.bochaai.com/v1/web-search"
    TIMEOUT_SECONDS = 30

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Bocha API key is required.")
        self.api_key = api_key
        self.search_mode = "search_api"
        self.last_error_class = ""
        self.last_error_message = ""

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        payload = {"query": query, "count": max(1, max_results), "summary": True}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(self.ENDPOINT, json=payload, headers=headers, timeout=self.TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            items = self._extract_items(data)
            results = [
                SearchResult(
                    title=(item.get("name") or item.get("title") or "").strip(),
                    url=(item.get("url") or item.get("link") or "").strip(),
                    content=(item.get("summary") or item.get("snippet") or item.get("content") or "").strip(),
                )
                for item in items
            ]
            self.last_error_class = ""
            self.last_error_message = ""
            return SearchResponse(query=query, results=[r for r in results if r.title or r.url or r.content])
        except requests.HTTPError as exc:
            error_class = classify_provider_error(exc)
            logger.error("Bocha search failed [%s] (HTTP %s): %s", error_class, getattr(exc.response, 'status_code', 0), exc)
            self.last_error_class = error_class
            self.last_error_message = str(exc)[:200]
            return SearchResponse(query=query, results=[])
        except Exception as exc:
            error_class = classify_provider_error(exc)
            logger.error("Bocha search failed [%s]: %s", error_class, exc)
            self.last_error_class = error_class
            self.last_error_message = str(exc)[:200]
            return SearchResponse(query=query, results=[])

    @staticmethod
    def _extract_items(data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        web_pages = data.get("webPages")
        if isinstance(web_pages, list):
            return web_pages
        if isinstance(web_pages, dict):
            value = web_pages.get("value")
            if isinstance(value, list):
                return value
        items = data.get("results")
        if isinstance(items, list):
            return items
        return []
