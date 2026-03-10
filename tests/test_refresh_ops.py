"""Tests for admin refresh orchestration endpoint."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main


def _seed_topic(db: ArcBriefDB, name: str) -> int:
    return db.create_topic(
        {
            "name": name,
            "keywords": [name.lower()],
            "rss_sources": [],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        }
    )


def test_refresh_ops_digest_regenerates_latest_available_digest(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "refresh_digest.db"))
    topic_id = _seed_topic(db, "AI Daily")
    db.save_brief(topic_id, "2026-03-10", "# AI Daily\n\nBrief body", 4)
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(
        main,
        "_generate_and_store_daily_digest",
        lambda date_str, language_used: {
            "date": date_str,
            "content": "# Daily Digest | 2026-03-10\n\nDigest body",
            "topic_count": 1,
            "missing_topics": [],
        },
    )

    result = main.refresh_ops(main.RefreshRequest(scope="digest", language="English (US)"))

    assert result["scope"] == "digest"
    assert result["digest"]["date"] == "2026-03-10"
    assert "Digest body" in result["digest"]["content"]


def test_refresh_ops_topic_refreshes_one_topic_and_returns_latest_brief(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "refresh_topic.db"))
    topic_id = _seed_topic(db, "AI Daily")
    db.save_brief(topic_id, "2026-03-10", "# AI Daily\n\nLatest topic brief", 5)
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "collect_topic", lambda tid: {"topic_id": tid, "topic_name": "AI Daily", "collected": 7, "saved": 6})
    monkeypatch.setattr(main, "generate_brief", lambda tid, payload=None: {"topic_id": tid, "topic_name": "AI Daily", "date": "2026-03-10", "items": 5})
    monkeypatch.setattr(main, "latest_brief", lambda tid: db.get_latest_brief(tid))

    result = main.refresh_ops(main.RefreshRequest(scope="topic", topic_id=topic_id, language="English (US)"))

    assert result["scope"] == "topic"
    assert result["collect"]["collected"] == 7
    assert result["brief_result"]["date"] == "2026-03-10"
    assert "Latest topic brief" in result["brief"]["content"]


def test_refresh_ops_all_runs_collect_brief_and_digest(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "refresh_all.db"))
    _seed_topic(db, "AI Daily")
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "collect_all", lambda: {"total_collected": 12, "total_saved": 10})
    captured = {}

    def fake_generate_brief_all(payload=None):
        captured["language"] = getattr(payload, "language", None)
        return {"date": "2026-03-10", "total_topics": 1, "results": [], "language_used": getattr(payload, "language", None)}

    monkeypatch.setattr(main, "generate_brief_all", fake_generate_brief_all)
    monkeypatch.setattr(
        main,
        "_generate_and_store_daily_digest",
        lambda date_str, language_used: {
            "date": date_str,
            "content": "# Daily Digest | 2026-03-10\n\nDigest body",
            "topic_count": 1,
            "missing_topics": [],
        },
    )

    result = main.refresh_ops(main.RefreshRequest(scope="all", language="Chinese (Simplified)"))

    assert result["scope"] == "all"
    assert result["collect"]["total_collected"] == 12
    assert result["briefs"]["date"] == "2026-03-10"
    assert result["briefs"]["language_used"] == "Chinese (Simplified)"
    assert captured["language"] == "Chinese (Simplified)"
    assert result["digest"]["date"] == "2026-03-10"
