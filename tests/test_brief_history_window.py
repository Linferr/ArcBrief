import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB


def test_list_briefs_respects_since_hours_window(tmp_path):
    db = ArcBriefDB(str(tmp_path / "brief_window.db"))
    topic_id = db.create_topic(
        {
            "name": "AI",
            "keywords": ["ai"],
            "rss_sources": [],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
            "is_active": True,
        }
    )
    db.save_brief(topic_id, "2026-02-20", "recent", 3)
    db.save_brief(topic_id, "2026-02-18", "old", 2)

    with db._connect() as conn:
        conn.execute(
            "UPDATE briefs SET created_at = datetime('now', '-2 hours') WHERE topic_id = ? AND date = ?",
            (topic_id, "2026-02-20"),
        )
        conn.execute(
            "UPDATE briefs SET created_at = datetime('now', '-72 hours') WHERE topic_id = ? AND date = ?",
            (topic_id, "2026-02-18"),
        )

    recent_only = db.list_briefs(topic_id, limit=30, since_hours=48)
    assert len(recent_only) == 1
    assert recent_only[0]["date"] == "2026-02-20"

    all_rows = db.list_briefs(topic_id, limit=30, since_hours=None)
    assert len(all_rows) == 2

