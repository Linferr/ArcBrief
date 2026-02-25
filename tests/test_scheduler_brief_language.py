"""Tests for scheduler brief task using app_config report language."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scheduler import ArcBriefScheduler


class _DummyDB:
    def __init__(self):
        self.saved = None
        self.logged = []

    def list_topics(self):
        return []

    def get_topic(self, topic_id):
        return SimpleNamespace(id=topic_id, name="AI Daily", push_channels=[])

    def get_recent_articles(self, topic_id, hours=48):
        return [{"title": "t1", "url": "https://example.com/1", "content": "c1"}]

    def get_app_config(self):
        return {"report_language": "Chinese (Simplified)"}

    def get_source_reputations(self, topic_id):
        return {"example.com": 1.0}

    def save_brief(self, topic_id, date_str, brief, item_count):
        self.saved = (topic_id, date_str, brief, item_count)

    def log_brief_run(self, topic_id, run_type, status, **kwargs):
        self.logged.append((topic_id, run_type, status, kwargs))


def test_scheduler_brief_task_passes_merged_config(monkeypatch):
    db = _DummyDB()
    scheduler = ArcBriefScheduler(db)
    captured = {}

    def _fake_build_brief(topic, items, source_weights=None, app_config=None):
        captured["topic"] = topic
        captured["items"] = items
        captured["source_weights"] = source_weights
        captured["app_config"] = app_config
        return "brief-content"

    monkeypatch.setattr("backend.scheduler.build_brief_for_topic", _fake_build_brief)

    scheduler._brief_task(7)

    assert captured["app_config"]["report_language"] == "Chinese (Simplified)"
    assert captured["source_weights"] == {"example.com": 1.0}
    assert db.saved is not None
    assert db.saved[2] == "brief-content"
