"""Search tool interfaces."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


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


def as_dict(value: Any) -> Dict[str, Any]:
    """Convert SDK response objects to plain dicts."""
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

