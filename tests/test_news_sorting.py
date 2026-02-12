import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import backend.main as main
from backend.db import ArcBriefDB


def test_parse_ts_for_sort_handles_sqlite_and_iso():
    sqlite_ts = "2026-02-09 10:30:00"
    iso_ts = "2026-02-09T10:30:00"
    assert main._parse_ts_for_sort(sqlite_ts).year == 2026
    assert main._parse_ts_for_sort(iso_ts).minute == 30


def test_get_articles_returns_time_source_and_time_sorted(tmp_path):
    db = ArcBriefDB(str(tmp_path / "test.db"))
    topic_id = db.create_topic(
        {
            "name": "T1",
            "keywords": ["ai"],
            "rss_sources": ["https://example.com/rss.xml"],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        }
    )

    now = datetime.utcnow()
    old = (now - timedelta(hours=3)).isoformat()
    newer = (now - timedelta(hours=1)).isoformat()

    db.save_articles(topic_id, [
        {
            "title": "older",
            "url": "https://example.com/a/older",
            "content": "x" * 80,
            "source": "rss",
            "published_at": old,
            "source_type": "rss",
        },
        {
            "title": "newer",
            "url": "https://example.com/a/newer",
            "content": "x" * 80,
            "source": "rss",
            "published_at": newer,
            "source_type": "rss",
        },
        {
            "title": "fallback",
            "url": "https://example.com/a/fallback",
            "content": "x" * 80,
            "source": "rss",
            "published_at": None,
            "source_type": "rss",
        },
    ])

    main.DB = db
    payload = main.get_articles(topic_id=topic_id, hours=48, sort="time", date=None)
    titles = [a["title"] for a in payload["articles"]]

    assert titles[0] == "fallback" or titles[0] == "newer"
    assert all("time_source" in a for a in payload["articles"])
    assert any(a["time_source"] == "published_at" for a in payload["articles"])
