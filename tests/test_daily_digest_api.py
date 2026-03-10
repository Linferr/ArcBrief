"""Tests for Phase 4-C daily digest generation and retrieval."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main


def _seed_topic(db: ArcBriefDB, name: str, active: bool = True) -> int:
    topic_id = db.create_topic(
        {
            "name": name,
            "keywords": [name.lower()],
            "rss_sources": [],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        }
    )
    if not active:
        db.update_topic(topic_id, {"is_active": False})
    return topic_id


def test_generate_daily_digest_persists_cross_topic_digest(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "daily_digest.db"))
    ai_id = _seed_topic(db, "AI Daily")
    global_id = _seed_topic(db, "Global Trending")
    policy_id = _seed_topic(db, "AI Policy & Safety")

    db.save_brief(ai_id, "2026-03-09", "# AI Daily\n\nAI developments summary.", 4)
    db.save_brief(global_id, "2026-03-09", "# Global Trending\n\nGlobal developments summary.", 5)

    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(
        main,
        "llm_chat",
        lambda system, user: "# Daily Digest | 2026-03-09\n\n## Executive Summary\nCombined daily digest.\n\n## Topic Highlights\n### AI Daily\nA.\n\n### Global Trending\nB.\n\n## Missing Topics\n- AI Policy & Safety",
    )

    result = main.generate_daily_digest(main.DigestGenerateRequest(date="2026-03-09"))

    assert result["date"] == "2026-03-09"
    assert result["topic_count"] == 2
    assert result["missing_topics"] == ["AI Policy & Safety"]
    assert "Combined daily digest." in result["content"]


def test_get_latest_digest_uses_latest_available_brief_date(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "latest_digest.db"))
    topic_id = _seed_topic(db, "AI Daily")
    db.save_brief(topic_id, "2026-03-08", "# AI Daily\n\nYesterday summary.", 3)

    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(
        main,
        "llm_chat",
        lambda system, user: "# Daily Digest | 2026-03-08\n\n## Executive Summary\nYesterday digest.\n\n## Topic Highlights\n### AI Daily\nYesterday summary.",
    )

    result = main.get_latest_digest()

    assert result["date"] == "2026-03-08"
    assert "Yesterday digest." in result["content"]

