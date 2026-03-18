import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main


def _setup_db(tmp_path):
    db = ArcBriefDB(str(tmp_path / "brief_anchor.db"))
    topic_id = db.create_topic(
        {
            "name": "AI Daily",
            "keywords": ["ai"],
            "rss_sources": [],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        }
    )
    db.save_brief(topic_id, "2026-03-06", "OpenAI shipping updates and agent orchestration changes.", 3)
    return db


def test_chat_prefers_explicit_brief_anchor(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)

    captured = {}

    def _fake_llm(system, user):
        captured["user"] = user
        return "anchored answer"

    monkeypatch.setattr(main, "llm_chat", _fake_llm)

    result = main.chat_with_briefs(
        main.ChatRequest(
            message="What changed?",
            topic_id=999,
            brief_id=1,
        )
    )

    assert result["reply"] == "anchored answer"
    assert result["context_layer"] == "brief_anchor"
    assert result["brief_id_used"] == 1
    assert result["context_warning"] is None
    assert "OpenAI shipping updates" in captured["user"]


def test_chat_invalid_brief_anchor_falls_back_with_warning(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "fallback answer")

    result = main.chat_with_briefs(main.ChatRequest(message="OpenAI news?", topic_id=1, brief_id=999))

    assert result["reply"] == "fallback answer"
    assert result["context_layer"] == "brief_context"
    assert result["brief_id_used"] is None
    assert result["context_warning"]


def test_run_job_injects_brief_anchor_context(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)

    captured = {}

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

    class _DummyAgent:
        def __init__(self, settings):
            self.search_meta = type(
                "Meta",
                (),
                {
                    "provider_requested": settings.search_provider,
                    "provider_effective": settings.search_provider,
                    "fallback_reason": "",
                    "llm_assisted_search": False,
                },
            )()
            self.last_state = type("State", (), {"delivery_status": "full", "gate_decision": "PASS", "blocking_issues": []})()

        def research(self, query, progress_cb=None, language="English (US)"):
            captured["query"] = query
            return "# Report"

        def save_report(self, report, output_dir):
            return os.path.join(output_dir, "brief_anchor_report.md")

    monkeypatch.setattr(main, "Settings", _DummySettings)
    monkeypatch.setattr(main, "QueryAgent", _DummyAgent)
    monkeypatch.setattr(main, "_build_model_candidates", lambda model: [model])

    run_id = "brief-anchor-run"
    main.RUNS[run_id] = main.RunRecord(run_id=run_id, query="What should we research next?")
    try:
        main._run_job(run_id=run_id, query="What should we research next?", language="English (US)", brief_id=1)
        assert "Brief anchor" in captured["query"]
        assert "#1" in captured["query"]
        assert any(event.stage == "brief_anchor" for event in main.RUNS[run_id].events)
    finally:
        main.RUNS.pop(run_id, None)


def test_start_run_passes_brief_id_to_background_job(monkeypatch):
    captured = {}

    class _DummyThread:
        def __init__(self, target, args, daemon):
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    class _DummyDB:
        def get_app_config(self):
            return {}

    monkeypatch.setattr(main, "threading", type("Threading", (), {"Thread": _DummyThread}))
    monkeypatch.setattr(main, "DB", _DummyDB())

    response = main.start_run(main.RunRequest(query="anchor test", language="English (US)", brief_id=42))

    assert response.run_id
    assert captured["args"][4] == 42
