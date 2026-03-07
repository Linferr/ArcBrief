"""Tests for Phase 4B bookmarks table and API."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main


def _setup_db(tmp_path):
    db = ArcBriefDB(str(tmp_path / "bookmarks.db"))
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
    db.save_brief(topic_id, "2026-03-07", "# Brief\n\ncontent", 3)
    brief = db.get_latest_brief(topic_id)
    return db, int(brief["id"])


def test_bookmark_create_and_list(tmp_path, monkeypatch):
    db, brief_id = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)

    result = main.create_bookmark(main.BookmarkCreateRequest(user_id="discord:42", brief_id=brief_id, note="save this"))
    listed = main.list_bookmarks("discord:42")

    assert result["status"] == "saved"
    assert listed["count"] == 1
    assert listed["items"][0]["brief_id"] == brief_id
    assert listed["items"][0]["topic_name"] == "AI Daily"
    assert listed["items"][0]["note"] == "save this"


def test_bookmark_upsert_updates_note_without_duplicates(tmp_path, monkeypatch):
    db, brief_id = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)

    main.create_bookmark(main.BookmarkCreateRequest(user_id="discord:42", brief_id=brief_id, note="first"))
    main.create_bookmark(main.BookmarkCreateRequest(user_id="discord:42", brief_id=brief_id, note="updated"))
    listed = main.list_bookmarks("discord:42")

    assert listed["count"] == 1
    assert listed["items"][0]["note"] == "updated"


def test_bookmark_delete_removes_saved_item(tmp_path, monkeypatch):
    db, brief_id = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)

    main.create_bookmark(main.BookmarkCreateRequest(user_id="discord:42", brief_id=brief_id, note=None))
    deleted = main.delete_bookmark("discord:42", brief_id)
    listed = main.list_bookmarks("discord:42")

    assert deleted["status"] == "deleted"
    assert listed["count"] == 0
