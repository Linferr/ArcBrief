"""Tests for Phase 5 starter packs API."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main


def test_list_starter_packs_returns_preview_metadata():
    packs = main.list_starter_packs()

    assert len(packs) >= 3
    first = packs[0].model_dump()
    assert first["id"]
    assert first["name"]
    assert first["ideal_for"]
    assert first["recommended_language"]
    assert isinstance(first["topics"], list)
    assert first["topics"][0]["name"]
    assert "rss_count" in first["topics"][0]


def test_apply_starter_pack_creates_missing_topics_and_skips_existing(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "starter_packs.db"))
    existing_topic_id = db.create_topic(
        {
            "name": "AI Daily",
            "keywords": ["ai"],
            "rss_sources": ["https://example.com/rss.xml"],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
            "is_active": True,
        }
    )
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "SCHEDULER", None)

    result = main.apply_starter_pack(main.StarterPackApplyRequest(pack_id="ai-founder-daily"))

    assert result["pack_id"] == "ai-founder-daily"
    assert result["created_count"] >= 1
    assert "AI Daily" in result["existing_topics"]
    names = [topic.name for topic in db.list_topics()]
    assert "AI Daily" in names
    assert "AI Builder Signals" in names
    assert "AI Policy & Safety" in names
    # Existing topic should not be duplicated.
    assert names.count("AI Daily") == 1
    assert db.get_topic(existing_topic_id) is not None
