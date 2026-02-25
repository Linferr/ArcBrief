"""Tests for _cleanup_inmemory_runs() TTL and capacity eviction (Phase 3A)."""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.state import RUNS, RunRecord


def _make_finished(run_id: str, finished_hours_ago: float) -> RunRecord:
    r = RunRecord(run_id=run_id, query="q", status="done")
    r.started_at = (datetime.utcnow() - timedelta(hours=finished_hours_ago + 0.1)).isoformat()
    r.finished_at = (datetime.utcnow() - timedelta(hours=finished_hours_ago)).isoformat()
    return r


def test_ttl_removes_old_finished_runs(monkeypatch):
    import backend.main as m
    monkeypatch.setattr(m, "RUNS_TTL_HOURS", 1)
    monkeypatch.setattr(m, "RUNS_MAX_RECORDS", 500)
    RUNS.clear()
    RUNS["old"] = _make_finished("old", finished_hours_ago=2.0)
    RUNS["fresh"] = _make_finished("fresh", finished_hours_ago=0.1)
    removed = m._cleanup_inmemory_runs()
    assert removed >= 1
    assert "old" not in RUNS
    assert "fresh" in RUNS


def test_cap_removes_oldest_when_overflow(monkeypatch):
    import backend.main as m
    monkeypatch.setattr(m, "RUNS_TTL_HOURS", 999)  # disable TTL eviction
    monkeypatch.setattr(m, "RUNS_MAX_RECORDS", 2)
    RUNS.clear()
    for i in range(5):
        # r0 is oldest (5h ago), r4 is newest (1h ago)
        RUNS[f"r{i}"] = _make_finished(f"r{i}", finished_hours_ago=float(5 - i))
    m._cleanup_inmemory_runs()
    assert len(RUNS) <= 2
    # newest runs should survive
    assert "r4" in RUNS
    assert "r3" in RUNS


def test_queued_job_without_anchor_survives_ttl(monkeypatch):
    import backend.main as m
    monkeypatch.setattr(m, "RUNS_TTL_HOURS", 1)
    monkeypatch.setattr(m, "RUNS_MAX_RECORDS", 500)
    RUNS.clear()
    # Queued job: no started_at and no finished_at, so TTL should not evict it
    r = RunRecord(run_id="queued", query="q", status="queued")
    RUNS["queued"] = r
    m._cleanup_inmemory_runs()
    assert "queued" in RUNS

