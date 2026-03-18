"""State models for the query agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


def _coerce_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    cleaned: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


@dataclass
class SearchItem:
    query: str
    title: str
    url: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CriticResult:
    overall_score: int
    gate_decision: str
    blocking_issues: List[str] = field(default_factory=list)
    suggested_queries: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    critique: str = ""
    source_gaps: str = ""

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], fallback_query: str = "") -> "CriticResult":
        critique = str(payload.get("critique", "") or "").strip()
        source_gaps = str(payload.get("source_gaps", "") or "").strip()
        gate_decision = str(payload.get("gate_decision", "REVISE") or "REVISE").strip().upper()
        if gate_decision not in {"PASS", "REVISE", "REJECT"}:
            gate_decision = "REVISE"

        try:
            overall_score = int(payload.get("overall_score", 2))
        except (TypeError, ValueError):
            overall_score = 2
        overall_score = max(1, min(5, overall_score))

        suggested_queries = _coerce_string_list(
            payload.get("suggested_queries", payload.get("suggested_search_queries"))
        )
        if not suggested_queries and fallback_query:
            suggested_queries = [fallback_query]

        questions = _coerce_string_list(payload.get("questions"))
        blocking_issues = _coerce_string_list(payload.get("blocking_issues"))
        if not blocking_issues and gate_decision != "PASS":
            blocking_issues = [text for text in (source_gaps, critique) if text]

        return cls(
            overall_score=overall_score,
            gate_decision=gate_decision,
            blocking_issues=blocking_issues,
            suggested_queries=suggested_queries,
            questions=questions,
            critique=critique,
            source_gaps=source_gaps,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "gate_decision": self.gate_decision,
            "blocking_issues": list(self.blocking_issues),
            "suggested_queries": list(self.suggested_queries),
            "suggested_search_queries": list(self.suggested_queries),
            "questions": list(self.questions),
            "critique": self.critique,
            "source_gaps": self.source_gaps,
        }


@dataclass
class ParagraphState:
    title: str
    content: str
    latest_summary: str = ""
    search_history: List[SearchItem] = field(default_factory=list)
    source_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    reflection_count: int = 0
    host_critiques: List[Dict[str, str]] = field(default_factory=list)
    fallback_reason: str = ""


@dataclass
class ReportState:
    query: str
    paragraphs: List[ParagraphState] = field(default_factory=list)
    global_source_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    next_source_index: int = 1
    final_report: str = ""
    planning_template: str = "industry_brief"
    delivery_status: str = "full"
    gate_decision: str = "PASS"
    blocking_issues: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()
