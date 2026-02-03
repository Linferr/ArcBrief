"""SQLite storage for ArcBrief (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class TopicRecord:
    id: int
    name: str
    keywords: List[str]
    rss_sources: List[str]
    scrape_frequency_hours: int
    push_time: str
    push_channels: List[str]
    is_active: bool


class ArcBriefDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    rss_sources TEXT NOT NULL,
                    scrape_frequency_hours INTEGER DEFAULT 4,
                    push_time TEXT DEFAULT '08:00',
                    push_channels TEXT DEFAULT '["discord"]',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    content TEXT,
                    source TEXT,
                    published_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(topic_id) REFERENCES topics(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS briefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    item_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(topic_id, date),
                    FOREIGN KEY(topic_id) REFERENCES topics(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    brief_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    item_count INTEGER DEFAULT 0,
                    summary_quality_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(brief_id) REFERENCES briefs(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS brief_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_collected INTEGER DEFAULT 0,
                    items_saved INTEGER DEFAULT 0,
                    error_message TEXT,
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    FOREIGN KEY(topic_id) REFERENCES topics(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    rss_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_fetched INTEGER DEFAULT 0,
                    last_error TEXT,
                    last_checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(topic_id) REFERENCES topics(id)
                )
            """)

    def create_topic(self, data: Dict[str, Any]) -> int:
        keywords = json.dumps(data.get("keywords", []), ensure_ascii=False)
        rss_sources = json.dumps(data.get("rss_sources", []), ensure_ascii=False)
        push_channels = json.dumps(data.get("push_channels", ["discord"]), ensure_ascii=False)
        scrape_frequency_hours = int(data.get("scrape_frequency_hours", 4))
        push_time = data.get("push_time", "08:00")
        is_active = 1 if data.get("is_active", True) else 0
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO topics (name, keywords, rss_sources, scrape_frequency_hours, push_time, push_channels, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("name", ""),
                    keywords,
                    rss_sources,
                    scrape_frequency_hours,
                    push_time,
                    push_channels,
                    is_active,
                ),
            )
            return int(cur.lastrowid)

    def list_topics(self) -> List[TopicRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM topics ORDER BY id DESC").fetchall()
        return [self._row_to_topic(r) for r in rows]

    def count_topics(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS cnt FROM topics").fetchone()
        return int(row["cnt"]) if row else 0

    def get_topic(self, topic_id: int) -> Optional[TopicRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        return self._row_to_topic(row) if row else None

    def save_articles(self, topic_id: int, items: Iterable[Dict[str, Any]]) -> int:
        count = 0
        with self._connect() as conn:
            for item in items:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO articles (topic_id, title, url, content, source, published_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            topic_id,
                            item.get("title", ""),
                            item.get("url", ""),
                            item.get("content", ""),
                            item.get("source", ""),
                            item.get("published_at"),
                        ),
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    continue
        return count

    def get_recent_articles(self, topic_id: int, hours: int = 24) -> List[Dict[str, Any]]:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE topic_id = ?
                  AND (published_at IS NULL OR published_at >= ?)
                ORDER BY published_at DESC, created_at DESC
                """,
                (topic_id, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_brief(self, topic_id: int, date_str: str, content: str, item_count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO briefs (topic_id, date, content, item_count)
                VALUES (?, ?, ?, ?)
                """,
                (topic_id, date_str, content, item_count),
            )

    def get_latest_brief(self, topic_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM briefs
                WHERE topic_id = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (topic_id,),
            ).fetchone()
        return dict(row) if row else None

    def _row_to_topic(self, row: sqlite3.Row) -> TopicRecord:
        return TopicRecord(
            id=int(row["id"]),
            name=row["name"],
            keywords=json.loads(row["keywords"] or "[]"),
            rss_sources=json.loads(row["rss_sources"] or "[]"),
            scrape_frequency_hours=int(row["scrape_frequency_hours"] or 4),
            push_time=row["push_time"] or "08:00",
            push_channels=json.loads(row["push_channels"] or "[]"),
            is_active=bool(row["is_active"]),
        )
