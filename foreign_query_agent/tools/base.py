"""Search tool interfaces."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


@dataclass
class SearchResponse:
    query: str
    results: List[SearchResult] = field(default_factory=list)


class SearchTool:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        raise NotImplementedError

