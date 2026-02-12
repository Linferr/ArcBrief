import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB


def _create_legacy_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            keywords TEXT NOT NULL,
            rss_sources TEXT NOT NULL,
            scrape_frequency_hours INTEGER DEFAULT 4,
            push_time TEXT DEFAULT '08:00',
            push_channels TEXT DEFAULT '[\"discord\"]',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            item_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(topic_id, date)
        )
    """)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute(
        "INSERT INTO topics (name, keywords, rss_sources, scrape_frequency_hours, push_time, push_channels, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Legacy Topic", "[]", "[]", 4, "08:00", "[\"discord\"]", 1),
    )
    conn.commit()
    conn.close()


def test_legacy_briefs_unique_constraint_is_migrated(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    db = ArcBriefDB(str(db_path))

    db.save_brief(1, "2026-02-09", "v1", 1)
    db.save_brief(1, "2026-02-09", "v2", 2)

    briefs = db.list_briefs(1, limit=10)
    assert len(briefs) >= 2
