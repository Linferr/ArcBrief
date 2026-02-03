"""Tavily search tool wrapper."""

from typing import Optional

from .base import SearchTool, SearchResponse, SearchResult

try:
    from tavily import TavilyClient
except Exception:  # pragma: no cover
    TavilyClient = None


class TavilySearchTool(SearchTool):
    DEFAULT_TIMEOUT = 30  # 30 seconds for search
    MAX_RETRIES = 2

    def __init__(self, api_key: str):
        if TavilyClient is None:
            raise RuntimeError("tavily-python is not installed.")
        if not api_key:
            raise ValueError("Tavily API key is required.")
        self.client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        import time

        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = self.client.search(
                    query=query,
                    max_results=max_results,
                    search_depth="basic",
                    timeout=self.DEFAULT_TIMEOUT,
                )
                results = [
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                    )
                    for item in resp.get("results", [])
                ]
                return SearchResponse(query=resp.get("query", query), results=results)
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                break

        # All retries failed - return empty results instead of crashing
        print(f"[WARN] Tavily search failed after {self.MAX_RETRIES + 1} attempts: {last_error}")
        return SearchResponse(query=query, results=[])

