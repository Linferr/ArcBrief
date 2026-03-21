import os
import sqlite3
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as m
from backend.db import ArcBriefDB
from backend.state import RUNS, RunRecord
from foreign_query_agent.tools import factory as f


class _DummySettings:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.llm_model = "qwen3-max"
        self.search_provider = "Bocha Search"
        self.research_strict_provider = True
        self.research_recency_mode = "recent_12m_with_90d_anchor"
        self.max_reflections = 3
        self.llm_api_key = "dummy"
        self.llm_base_url = "http://dummy"
        self.tavily_api_key = "tv"
        self.bocha_api_key = "bk"
        self.zhipu_api_key = ""
        self.zhipu_openai_base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.zhipu_web_search_model = "glm-4-plus"
        self.exa_api_key = ""
        self.volcengine_api_key = ""
        self.volcengine_openai_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.volcengine_model_ep = ""


class _DummyMetricsAgent:
    def __init__(self, settings):
        self.search_meta = f.SearchToolBuildMeta(
            provider_requested=settings.search_provider,
            provider_effective="Tavily Search API",
            fallback_reason="Bocha Search unavailable: missing",
            llm_assisted_search=False,
        )
        self.last_state = SimpleNamespace(
            spec=SimpleNamespace(
                premise_status="invalid",
                original_query="chatgpt5.4 updates and optimization",
                effective_query=(
                    "Verify whether ChatGPT-5.4 is an official OpenAI release and summarize actual recent OpenAI updates."
                ),
                report_type_requested="industry_brief",
                report_type_effective="claim_audit",
            ),
            delivery_status="full",
            gate_decision="PASS",
            blocking_issues=[],
            report_type="claim_audit",
            report_type_requested="industry_brief",
            report_type_effective="claim_audit",
            planning_template="claim_audit",
            report_shape="long_analysis",
            length_preset="long",
            quality_mode="quality_first",
            final_report="# Report\n\n## Official Status Check\nAlpha.\n\n## Practical Takeaways\nBeta.",
            section_assessments=[
                {
                    "title": "Official Status Check",
                    "gate_decision": "PASS",
                    "overall_score": 4,
                    "primary_source_count": 2,
                    "source_count": 3,
                }
            ],
            global_source_map={
                "S1": {"title": "Primary note", "url": "https://openai.com/blog/post", "source_type": "primary"},
                "S2": {"title": "Secondary coverage", "url": "https://example.com/report", "source_type": "secondary"},
                "S3": {
                    "title": "OpenAI models docs",
                    "url": "https://platform.openai.com/docs/models",
                    "source_type": "primary",
                },
            },
        )

    def research(self, query, progress_cb=None, language="English (US)", report_type=None, length_preset="long"):
        events = [
            {"stage": "premise_check", "message": "premise=invalid reframed=true report_type=claim_audit", "run_id": "unit"},
            {"stage": "outline", "message": "Outline generated", "run_id": "unit"},
            {"stage": "search", "message": "Search: first query", "run_id": "unit"},
            {"stage": "summary", "message": "Summary round 1 ready", "round": 1, "run_id": "unit"},
            {
                "stage": "critic_gate",
                "message": "decision=PASS score=4 blocking=none official_sources=2",
                "round": 1,
                "run_id": "unit",
            },
            {"stage": "final", "message": "Report formatted", "run_id": "unit"},
        ]
        if progress_cb:
            for evt in events:
                progress_cb(evt)
        return "# Report"

    def save_report(self, report, output_dir):
        return os.path.join(output_dir, "metrics_report.md")

    def llm_usage_summary(self):
        return {
            "request_count": 7,
            "prompt_tokens": 2100,
            "completion_tokens": 1400,
            "total_tokens": 3500,
            "estimated_cost_usd": 0.42,
            "model_requested": "qwen3-max",
            "model_effective": "qwen3-max",
        }


class _DummyDB:
    def __init__(self):
        self.saved_runs = []

    def get_app_config(self):
        return {
            "search_provider": "Bocha Search",
            "primary_model": "Qwen3 MAX",
            "critical_analysis_layer": True,
        }

    def save_research_run(self, **kwargs):
        self.saved_runs.append(kwargs)

    def list_research_runs(self, limit=200):
        return [
            {
                "run_id": "db_metrics",
                "query": "db query",
                "status": "done",
                "language_used": "English (US)",
                "report_path": "outputs/db_metrics.md",
                "report_content": "# Report",
                "started_at": "2026-03-17T10:00:00",
                "finished_at": "2026-03-17T10:01:30",
                "created_at": "2026-03-17T10:00:00",
                "delivery_status": "full",
                "gate_decision": "PASS",
                "blocking_issues": [],
                "metrics_summary": {
                    "task_completion": True,
                    "total_duration_sec": 90,
                    "step_count": 6,
                    "search_calls": 2,
                    "reflection_rounds": 0,
                    "fallback_triggered": False,
                    "provider_effective": "Exa Search",
                    "provider_fallback_reason": "",
                    "premise_status": "valid",
                    "query_reframed": False,
                    "original_query": "db query",
                    "effective_query": "db query",
                    "report_type_requested": "company_analysis",
                    "report_type_effective": "company_analysis",
                    "official_source_count": 1,
                },
            }
        ]

    def get_research_run(self, run_id):
        if run_id == "db_metrics":
            return self.list_research_runs()[0]
        return None


def _create_legacy_research_runs_db(path):
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
            delivery_status TEXT DEFAULT 'full',
            gate_decision TEXT,
            blocking_issues TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO schema_migrations(version) VALUES (9)")
    conn.commit()
    conn.close()


def test_run_job_computes_metrics_summary(monkeypatch):
    monkeypatch.setattr(m, "Settings", _DummySettings)
    monkeypatch.setattr(m, "QueryAgent", _DummyMetricsAgent)
    monkeypatch.setattr(m, "_build_model_candidates", lambda model: [model])

    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "unit-metrics"
    RUNS[run_id] = RunRecord(run_id=run_id, query="quality signals")
    try:
        m._run_job(run_id=run_id, query="quality signals", language="English (US)")
        record = RUNS[run_id]
        summary = record.metrics_summary
        assert summary["task_completion"] is True
        assert summary["step_count"] == len(record.events)
        assert summary["search_calls"] == 1
        assert summary["reflection_rounds"] == 0
        assert summary["fallback_triggered"] is True
        assert summary["provider_effective"] == "Tavily Search API"
        assert summary["provider_fallback_reason"] == "Bocha Search unavailable: missing"
        assert summary["premise_status"] == "invalid"
        assert summary["query_reframed"] is True
        assert summary["original_query"] == "chatgpt5.4 updates and optimization"
        assert "official OpenAI release" in summary["effective_query"]
        assert summary["report_type"] == "claim_audit"
        assert summary["report_type_requested"] == "industry_brief"
        assert summary["report_type_effective"] == "claim_audit"
        assert summary["planning_template"] == "claim_audit"
        assert summary["report_shape"] == "long_analysis"
        assert summary["length_preset"] == "long"
        assert summary["quality_mode"] == "quality_first"
        assert summary["prompt_tokens"] == 2100
        assert summary["completion_tokens"] == 1400
        assert summary["total_tokens"] == 3500
        assert summary["estimated_cost_usd"] == 0.42
        assert summary["word_count"] >= 5
        assert summary["primary_source_count"] == 2
        assert summary["official_source_count"] == 2
        assert summary["section_gate_results"][0]["title"] == "Official Status Check"
        assert isinstance(summary["total_duration_sec"], int)
        assert db.saved_runs[-1]["metrics_summary"]["search_calls"] == 1
    finally:
        RUNS.pop(run_id, None)


def test_status_and_history_expose_metrics_summary(monkeypatch):
    db = _DummyDB()
    monkeypatch.setattr(m, "DB", db)

    run_id = "memory_metrics"
    RUNS[run_id] = RunRecord(
        run_id=run_id,
        query="memory query",
        status="done",
        report_type="claim_audit",
        report_shape="long_analysis",
        length_preset="long",
        planning_template="claim_audit",
        premise_status="invalid",
        query_reframed=True,
        original_query="chatgpt5.4 updates",
        effective_query="Verify whether ChatGPT-5.4 exists and summarize actual OpenAI updates",
        report_type_requested="industry_brief",
        report_type_effective="claim_audit",
        word_count=120,
        prompt_tokens=500,
        completion_tokens=300,
        estimated_cost_usd=0.08,
        primary_source_count=2,
        section_gate_results=[{"title": "Official Status Check", "gate_decision": "PASS"}],
        metrics_summary={
            "task_completion": True,
            "total_duration_sec": 12,
            "step_count": 4,
            "search_calls": 1,
            "reflection_rounds": 0,
            "fallback_triggered": False,
            "provider_effective": "Tavily Search API",
            "provider_fallback_reason": "",
            "premise_status": "invalid",
            "query_reframed": True,
            "original_query": "chatgpt5.4 updates",
            "effective_query": "Verify whether ChatGPT-5.4 exists and summarize actual OpenAI updates",
            "report_type_requested": "industry_brief",
            "report_type_effective": "claim_audit",
            "official_source_count": 2,
        },
    )
    try:
        status = m.get_status(run_id)
        assert status.metrics_summary["step_count"] == 4
        assert status.metrics_summary["provider_effective"] == "Tavily Search API"
        assert status.report_type == "claim_audit"
        assert status.premise_status == "invalid"
        assert status.query_reframed is True
        assert status.report_type_requested == "industry_brief"
        assert status.report_type_effective == "claim_audit"
        assert status.official_source_count == 2
        assert status.word_count == 120
        assert status.prompt_tokens == 500
        assert status.estimated_cost_usd == 0.08
        assert status.section_gate_results[0]["title"] == "Official Status Check"

        history = m.get_history()
        memory_item = next(item for item in history["results"] if item["run_id"] == run_id)
        db_item = next(item for item in history["results"] if item["run_id"] == "db_metrics")
        assert memory_item["metrics_summary"]["search_calls"] == 1
        assert db_item["metrics_summary"]["total_duration_sec"] == 90
        assert memory_item["report_type"] == "claim_audit"
        assert memory_item["premise_status"] == "invalid"
        assert memory_item["query_reframed"] is True
        assert memory_item["report_type_requested"] == "industry_brief"
        assert memory_item["report_type_effective"] == "claim_audit"
        assert memory_item["official_source_count"] == 2
        assert memory_item["word_count"] == 120
        assert memory_item["estimated_cost_usd"] == 0.08
    finally:
        RUNS.pop(run_id, None)


def test_metrics_summary_migration_and_round_trip(tmp_path):
    db_path = tmp_path / "legacy_metrics.db"
    _create_legacy_research_runs_db(db_path)

    db = ArcBriefDB(str(db_path))
    db.save_research_run(
        run_id="run_1",
        query="q",
        status="done",
        language_used="English (US)",
        report_path="outputs/run_1.md",
        report_content="# Report",
        started_at="2026-03-17T10:00:00",
        finished_at="2026-03-17T10:01:00",
        delivery_status="full",
        gate_decision="PASS",
        blocking_issues=[],
        metrics_summary={
            "task_completion": True,
            "total_duration_sec": 60,
            "step_count": 5,
            "search_calls": 2,
            "reflection_rounds": 1,
            "fallback_triggered": False,
            "provider_effective": "Exa Search",
            "provider_fallback_reason": "",
            "premise_status": "valid",
            "query_reframed": False,
            "original_query": "q",
            "effective_query": "q",
            "report_type_requested": "company_analysis",
            "report_type_effective": "company_analysis",
            "official_source_count": 1,
        },
    )

    row = db.get_research_run("run_1")
    assert row is not None
    assert row["metrics_summary"]["step_count"] == 5
    assert row["metrics_summary"]["provider_effective"] == "Exa Search"
    assert row["metrics_summary"]["premise_status"] == "valid"
    assert row["metrics_summary"]["official_source_count"] == 1
