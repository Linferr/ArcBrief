import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as m
from backend.db import ArcBriefDB
from backend.state import RUNS, RunRecord


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.llm_model = "qwen3-max"
        self.search_provider = "Tavily Search API"
        self.research_strict_provider = True
        self.research_recency_mode = "recent_12m_with_90d_anchor"
        self.max_reflections = 3
        self.llm_api_key = "dummy"
        self.llm_base_url = "http://dummy"
        self.tavily_api_key = "tv"
        self.bocha_api_key = ""
        self.zhipu_api_key = ""
        self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.zhipu_web_search_model = "glm-4-plus"
        self.exa_api_key = ""
        self.volcengine_api_key = ""
        self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.volcengine_model_ep = ""


class _DummyBlockedAgent:
    def __init__(self, settings):
        self.search_meta = SimpleNamespace(
            provider_requested=settings.search_provider,
            provider_effective="Tavily Search API",
            fallback_reason="",
            llm_assisted_search=False,
        )
        self.last_state = None

    def research(self, query, progress_cb=None, language="English (US)"):
        if progress_cb:
            progress_cb(
                {
                    "stage": "critic_gate",
                    "message": "decision=REJECT score=1 blocking=Timeline claims are unsupported.",
                    "run_id": "unit",
                }
            )
            progress_cb(
                {
                    "stage": "final",
                    "message": "Report blocked by critic gate",
                    "run_id": "unit",
                }
            )
        self.last_state = SimpleNamespace(
            delivery_status="limited",
            gate_decision="REJECT",
            blocking_issues=["Timeline claims are unsupported."],
        )
        return "# Research Gate Notice\n\n## Blocking Issues\n- Timeline claims are unsupported.\n"

    def save_report(self, report, output_dir):
        return os.path.join(output_dir, "blocked_report.md")


class _DummyDB:
    def __init__(self):
        self.saved_runs = []

    def get_app_config(self):
        return {}

    def save_research_run(self, **kwargs):
        self.saved_runs.append(kwargs)

    def list_research_runs(self, limit=200):
        return [
            {
                "run_id": "db_blocked",
                "query": "db query",
                "status": "done",
                "language_used": "English (US)",
                "report_path": "outputs/db_blocked.md",
                "report_content": "# Research Gate Notice",
                "started_at": "2026-03-17T10:00:00",
                "finished_at": "2026-03-17T10:01:00",
                "created_at": "2026-03-17T10:00:00",
                "delivery_status": "limited",
                "gate_decision": "REJECT",
                "blocking_issues": ["DB persisted issue"],
            }
        ]

    def get_research_run(self, run_id):
        if run_id == "db_blocked":
            return self.list_research_runs()[0]
        return None


def _create_legacy_research_runs_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE research_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            query TEXT NOT NULL,
            status TEXT NOT NULL,
            language_used TEXT,
            report_path TEXT,
            report_content TEXT,
            started_at TEXT,
            finished_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO schema_migrations(version) VALUES (6)")
    conn.commit()
    conn.close()


def test_run_job_marks_limited_delivery_when_agent_gate_blocks(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _DummyBlockedAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])

    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-blocked-delivery"
    RUNS[run_id] = RunRecord(run_id=run_id, query="timeline risk")
    try:
        m._run_job(run_id=run_id, query="timeline risk", language="English (US)")
        record = RUNS[run_id]
        assert record.status == "done"
        assert record.delivery_status == "limited"
        assert record.gate_decision == "REJECT"
        assert record.blocking_issues == ["Timeline claims are unsupported."]
        assert db.saved_runs[-1]["delivery_status"] == "limited"
        assert db.saved_runs[-1]["gate_decision"] == "REJECT"
        assert db.saved_runs[-1]["blocking_issues"] == ["Timeline claims are unsupported."]
    finally:
        RUNS.pop(run_id, None)


def test_status_and_history_expose_delivery_semantics(monkeypatch):
    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "memory_blocked"
    RUNS[run_id] = RunRecord(
        run_id=run_id,
        query="memory query",
        status="done",
        report_content="# Research Gate Notice",
        delivery_status="limited",
        gate_decision="REJECT",
        blocking_issues=["Memory blocked issue"],
    )
    try:
        status = m.get_status(run_id)
        assert status.delivery_status == "limited"
        assert status.gate_decision == "REJECT"
        assert status.blocking_issues == ["Memory blocked issue"]

        history = m.get_history()
        memory_item = next(item for item in history["results"] if item["run_id"] == run_id)
        db_item = next(item for item in history["results"] if item["run_id"] == "db_blocked")
        assert memory_item["delivery_status"] == "limited"
        assert memory_item["gate_decision"] == "REJECT"
        assert db_item["delivery_status"] == "limited"
        assert db_item["gate_decision"] == "REJECT"
    finally:
        RUNS.pop(run_id, None)


def test_research_run_delivery_columns_migrate_and_round_trip(tmp_path):
    db_path = tmp_path / "legacy_runs.db"
    _create_legacy_research_runs_db(db_path)

    db = ArcBriefDB(str(db_path))
    db.save_research_run(
        run_id="run_1",
        query="q",
        status="done",
        language_used="English (US)",
        report_path="outputs/run_1.md",
        report_content="# Research Gate Notice",
        started_at="2026-03-17T10:00:00",
        finished_at="2026-03-17T10:01:00",
        delivery_status="limited",
        gate_decision="REJECT",
        blocking_issues=["Insufficient primary sources"],
    )

    row = db.get_research_run("run_1")
    assert row is not None
    assert row["delivery_status"] == "limited"
    assert row["gate_decision"] == "REJECT"
    assert row["blocking_issues"] == ["Insufficient primary sources"]
