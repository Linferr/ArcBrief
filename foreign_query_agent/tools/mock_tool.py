"""Mock search tool for offline tests."""

from .base import SearchTool, SearchResponse, SearchResult


class MockSearchTool(SearchTool):
    def search(self, query: str, max_results: int = 3) -> SearchResponse:
        results = [
            SearchResult(
                title=f"Mock result {i+1} for {query}",
                url=f"https://example.com/{i+1}",
                content=f"This is mock content for {query} (item {i+1}).",
            )
            for i in range(max_results)
        ]
        return SearchResponse(query=query, results=results)

