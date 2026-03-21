import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as m
from backend.state import RUNS, RunRecord


class _MetricsDB:
    def list_research_runs(self, limit=200):
        return [
            {
                "run_id": "db_done_a",
                "query": "company analysis",
                "status": "done",
                "language_used": "English (US)",
                "started_at": "2026-03-20T10:00:00",
                "finished_at": "2026-03-20T10:05:00",
                "delivery_status": "full",
                "gate_decision": "PASS",
                "blocking_issues": [],
                "metrics_summary": {
                    "task_completion": True,
                    "total_duration_sec": 300,
                    "estimated_cost_usd": 0.5,
                    "provider_effective": "Volcano Engine",
                    "report_type": "company_analysis",
                    "primary_source_count": 2,
                    "premise_status": "valid",
                    "report_type_effective": "company_analysis",
                },
            },
            {
                "run_id": "db_done_b",
                "query": "policy analysis",
                "status": "done",
                "language_used": "English (US)",
                "started_at": "2026-03-20T11:00:00",
                "finished_at": "2026-03-20T11:04:00",
                "delivery_status": "limited",
                "gate_decision": "REVISE",
                "blocking_issues": ["Need more primary evidence"],
                "metrics_summary": {
                    "task_completion": True,
                    "total_duration_sec": 240,
                    "estimated_cost_usd": 0.25,
                    "provider_effective": "Tavily Search API",
                    "report_type": "policy_analysis",
                    "primary_source_count": 0,
                    "premise_status": "invalid",
                    "report_type_effective": "claim_audit",
                },
            },
        ]


def test_product_metrics_aggregates_cost_quality_and_duration(monkeypatch):
    monkeypatch.setattr(m, "DB", _MetricsDB())
    original_runs = dict(RUNS)
    RUNS.clear()
    RUNS["memory_done"] = RunRecord(
        run_id="memory_done",
        query="person profile",
        status="done",
        started_at="2026-03-20T12:00:00",
        finished_at="2026-03-20T12:03:00",
        report_type="person_profile",
        report_type_effective="person_profile",
        premise_status="valid",
        delivery_status="full",
        gate_decision="PASS",
        primary_source_count=1,
        metrics_summary={
            "task_completion": True,
            "total_duration_sec": 180,
            "estimated_cost_usd": 0.15,
            "provider_effective": "Volcano Engine",
            "report_type": "person_profile",
            "report_type_effective": "person_profile",
            "primary_source_count": 1,
            "premise_status": "valid",
        },
    )
    try:
        payload = m.get_product_metrics(days=7)

        assert payload["total_runs"] == 3
        assert payload["task_completion_rate"] == 1.0
        assert payload["limited_delivery_rate"] == 1 / 3
        assert payload["gate_pass_rate"] == 2 / 3
        assert payload["avg_cost_per_run"] == 0.3
        assert payload["total_estimated_cost_usd"] == 0.9
        assert payload["avg_duration_sec"] == 240
        assert payload["primary_source_coverage_rate"] == 2 / 3
        assert payload["premise_invalid_rate"] == 1 / 3
        assert payload["by_report_type"]["company_analysis"]["count"] == 1
        assert payload["by_provider"]["Volcano Engine"]["count"] == 2
    finally:
        RUNS.clear()
        RUNS.update(original_runs)
