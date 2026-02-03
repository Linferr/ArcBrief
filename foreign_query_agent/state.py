"""State models for the query agent."""

from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime


@dataclass
class SearchItem:
    query: str
    title: str
    url: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ParagraphState:
    title: str
    content: str
    latest_summary: str = ""
    search_history: List[SearchItem] = field(default_factory=list)
    reflection_count: int = 0
    host_critiques: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ReportState:
    query: str
    paragraphs: List[ParagraphState] = field(default_factory=list)
    final_report: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()

