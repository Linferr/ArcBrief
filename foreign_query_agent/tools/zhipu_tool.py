"""Zhipu OpenAI-compatible web search wrapper."""

from __future__ import annotations

from .base import SearchResponse, SearchTool
from .openai_compat_search import OpenAICompatWebSearchClient


class ZhipuSearchTool(SearchTool):
    """Zhipu web search tool built on OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAICompatWebSearchClient(
            provider_name="Zhipu Web Search",
            api_key=api_key,
            base_url=base_url,
            model=model,
            search_mode="web_search_tool",
        )
        self.search_mode = "web_search_tool"
        self.last_error_class = ""
        self.last_error_message = ""

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        response = self.client.search(query, max_results=max_results)
        self.last_error_class = self.client.last_error_class
        self.last_error_message = self.client.last_error_message
        return response
