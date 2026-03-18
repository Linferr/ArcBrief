"""In-memory run store for FastAPI backend."""

from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
from datetime import datetime


@dataclass
class RunEvent:
    stage: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    run_id: Optional[str] = None
    paragraph: Optional[str] = None
    paragraph_idx: Optional[int] = None
    total_paragraphs: Optional[int] = None
    round: Optional[int] = None


@dataclass
class RunRecord:
    run_id: str
    query: str
    run_type: str = "research"
    language_used: str = "English (US)"
    status: str = "queued"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    report_path: Optional[str] = None
    report_content: Optional[str] = None
    delivery_status: str = "full"
    gate_decision: Optional[str] = None
    blocking_issues: List[str] = field(default_factory=list)
    metrics_summary: Dict[str, Any] = field(default_factory=dict)
    events: List[RunEvent] = field(default_factory=list)


RUNS: Dict[str, RunRecord] = {}

