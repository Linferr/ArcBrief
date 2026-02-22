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
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_path TEXT,
                    report_content TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS brief_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    brief_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                    voter_key TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(brief_id) REFERENCES briefs(id),
                    UNIQUE(brief_id, voter_key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._run_migrations(conn)
            self._ensure_briefs_multi_version(conn)
            self._ensure_articles_topic_unique(conn)  # v5: topic-scoped URL uniqueness

    # ---------- Migrations ----------
    _MIGRATIONS: List[tuple] = [
        # (version, sql) — append new migrations here
        (1, "ALTER TABLE brief_feedback ADD COLUMN voter_key TEXT NOT NULL DEFAULT 'anonymous'"),
        (2, "CREATE UNIQUE INDEX IF NOT EXISTS idx_brief_feedback_unique ON brief_feedback(brief_id, voter_key)"),
        (4, """CREATE TABLE IF NOT EXISTS source_reputation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                source_domain TEXT NOT NULL,
                score REAL DEFAULT 0.0,
                vote_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(topic_id) REFERENCES topics(id),
                UNIQUE(topic_id, source_domain)
             )"""),
    ]

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations"
        ).fetchone()
        current = int(row["v"]) if row else 0
        for version, sql in self._MIGRATIONS:
            if version > current:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as exc:
                    msg = str(exc).lower()
                    if "duplicate column name" not in msg:
                        raise
                conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))

    def _has_unique_brief_per_day(self, conn: sqlite3.Connection) -> bool:
        for idx in conn.execute("PRAGMA index_list(briefs)").fetchall():
            # PRAGMA index_list columns: seq, name, unique, origin, partial
            if int(idx[2]) != 1:
                continue
            idx_name = idx[1]
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()]
            if cols == ["topic_id", "date"]:
                return True
        return False

    def _has_articles_topic_unique(self, conn: sqlite3.Connection) -> bool:
        """True only when UNIQUE(topic_id, url) exists AND no single-col UNIQUE(url) remains."""
        has_topic_url_unique = False
        has_url_only_unique = False
        for idx in conn.execute("PRAGMA index_list(articles)").fetchall():
            # PRAGMA index_list columns: seq, name, unique, origin, partial
            if int(idx[2]) != 1:  # not unique
                continue
            idx_name = idx[1]
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()]
            if cols == ["topic_id", "url"]:
                has_topic_url_unique = True
            elif cols == ["url"]:
                has_url_only_unique = True
        return has_topic_url_unique and not has_url_only_unique

    def _ensure_briefs_multi_version(self, conn: sqlite3.Connection) -> None:
        marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone()
        if marker:
            return
        if not self._has_unique_brief_per_day(conn):
            conn.execute("INSERT INTO schema_migrations (version) VALUES (3)")
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS briefs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                content TEXT NOT NULL,
                item_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(topic_id) REFERENCES topics(id)
            )
        """)
        conn.execute("""
            INSERT INTO briefs_new (id, topic_id, date, content, item_count, created_at)
            SELECT id, topic_id, date, content, item_count, created_at FROM briefs
        """)
        conn.execute("DROP TABLE briefs")
        conn.execute("ALTER TABLE briefs_new RENAME TO briefs")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO schema_migrations (version) VALUES (3)")

    def _ensure_articles_topic_unique(self, conn: sqlite3.Connection) -> None:
        """v5 migration: change articles UNIQUE(url) → UNIQUE(topic_id, url).
        Atomic: runs as individual conn.execute() calls within the outer
        with-conn transaction block; exception auto-rolls back everything."""
        # Primary idempotency guard (mirrors _ensure_briefs_multi_version pattern)
        marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 5").fetchone()
        if marker:
            return

        # Secondary guard: constraint already correct (e.g. manually fixed DB)
        if self._has_articles_topic_unique(conn):
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (5)")
            return

        # Clean up any leftover from a previously-interrupted attempt
        conn.execute("DROP TABLE IF EXISTS articles_new")

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE articles_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id     INTEGER NOT NULL,
                title        TEXT    NOT NULL,
                url          TEXT    NOT NULL,
                content      TEXT,
                source       TEXT,
                published_at TEXT,
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(topic_id) REFERENCES topics(id),
                UNIQUE(topic_id, url)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO articles_new
                (id, topic_id, title, url, content, source, published_at, created_at)
            SELECT id, topic_id, title, url, content, source, published_at, created_at
            FROM articles
        """)
        conn.execute("DROP TABLE articles")
        conn.execute("ALTER TABLE articles_new RENAME TO articles")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)")
        conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (5)")

    # ---------- brief_runs logging ----------
    def log_brief_run(self, topic_id: int, run_type: str, status: str,
                      items_collected: int = 0, items_saved: int = 0,
                      error_message: Optional[str] = None,
                      started_at: Optional[str] = None,
                      finished_at: Optional[str] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO brief_runs
                (topic_id, run_type, status, items_collected, items_saved, error_message, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (topic_id, run_type, status, items_collected, items_saved,
                 error_message, started_at or datetime.utcnow().isoformat(),
                 finished_at or datetime.utcnow().isoformat()),
            )

    def get_brief_run_stats(self, topic_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM brief_runs WHERE topic_id = ? ORDER BY started_at DESC LIMIT ?",
                (topic_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- rss_health ----------
    def upsert_rss_health(self, topic_id: int, rss_url: str, status: str,
                          items_fetched: int = 0, items_passed: int = 0,
                          last_error: Optional[str] = None) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM rss_health WHERE topic_id = ? AND rss_url = ?",
                (topic_id, rss_url),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE rss_health
                       SET status = ?, items_fetched = ?, last_error = ?,
                           last_checked_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (status, items_fetched, last_error, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO rss_health
                       (topic_id, rss_url, status, items_fetched, last_error)
                       VALUES (?, ?, ?, ?, ?)""",
                    (topic_id, rss_url, status, items_fetched, last_error),
                )

    def get_rss_health(self, topic_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rss_health WHERE topic_id = ? ORDER BY last_checked_at DESC",
                (topic_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_rss_health(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT rh.*, t.name AS topic_name
                   FROM rss_health rh
                   JOIN topics t ON t.id = rh.topic_id
                   ORDER BY rh.last_checked_at DESC""",
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- brief feedback ----------
    def save_brief_feedback(self, brief_id: int, rating: int, voter_key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO brief_feedback (brief_id, rating, voter_key)
                VALUES (?, ?, ?)
                ON CONFLICT(brief_id, voter_key)
                DO UPDATE SET rating = excluded.rating, created_at = CURRENT_TIMESTAMP
                """,
                (brief_id, rating, voter_key),
            )

    def get_brief_feedback_rating(self, brief_id: int, voter_key: str) -> Optional[int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rating FROM brief_feedback WHERE brief_id = ? AND voter_key = ?",
                (brief_id, voter_key),
            ).fetchone()
        if not row:
            return None
        try:
            return int(row["rating"])
        except Exception:
            return None

    def get_brief_feedback_stats(self, brief_id: int) -> Dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(CASE WHEN rating = 1 THEN 1 END) AS upvotes,
                    COUNT(CASE WHEN rating = -1 THEN 1 END) AS downvotes
                FROM brief_feedback WHERE brief_id = ?
                """,
                (brief_id,),
            ).fetchone()
        return {"upvotes": row["upvotes"] or 0, "downvotes": row["downvotes"] or 0} if row else {"upvotes": 0, "downvotes": 0}

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
                    cur = conn.execute(
                        """
                        INSERT INTO articles (topic_id, title, url, content, source, published_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(topic_id, url) DO UPDATE SET
                          title = CASE
                            WHEN TRIM(COALESCE(articles.title, '')) = '' AND TRIM(COALESCE(excluded.title, '')) != ''
                            THEN excluded.title ELSE articles.title
                          END,
                          content = CASE
                            WHEN LENGTH(TRIM(COALESCE(excluded.content, ''))) > LENGTH(TRIM(COALESCE(articles.content, '')))
                            THEN excluded.content ELSE articles.content
                          END,
                          source = CASE
                            WHEN TRIM(COALESCE(articles.source, '')) = '' AND TRIM(COALESCE(excluded.source, '')) != ''
                            THEN excluded.source ELSE articles.source
                          END,
                          published_at = CASE
                            WHEN articles.published_at IS NULL AND excluded.published_at IS NOT NULL
                            THEN excluded.published_at ELSE articles.published_at
                          END
                        WHERE
                          (TRIM(COALESCE(articles.title, '')) = '' AND TRIM(COALESCE(excluded.title, '')) != '')
                          OR (LENGTH(TRIM(COALESCE(excluded.content, ''))) > LENGTH(TRIM(COALESCE(articles.content, ''))))
                          OR (articles.published_at IS NULL AND excluded.published_at IS NOT NULL)
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
                    count += int(cur.rowcount or 0)
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
                  AND (
                    (published_at IS NOT NULL AND published_at >= ?)
                    OR (published_at IS NULL AND created_at >= ?)
                  )
                ORDER BY published_at DESC, created_at DESC
                """,
                (topic_id, since, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_brief(self, topic_id: int, date_str: str, content: str, item_count: int) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO briefs (topic_id, date, content, item_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (topic_id, date_str, content, item_count),
                )
            except sqlite3.IntegrityError:
                # Backward-compatible fallback when running on old DB schema before migration.
                conn.execute(
                    """
                    UPDATE briefs
                    SET content = ?, item_count = ?, created_at = CURRENT_TIMESTAMP
                    WHERE topic_id = ? AND date = ?
                    """,
                    (content, item_count, topic_id, date_str),
                )

    def get_brief_by_id(self, brief_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        return dict(row) if row else None

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

    def list_briefs(self, topic_id: int, limit: int = 14) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM briefs WHERE topic_id = ? ORDER BY created_at DESC LIMIT ?",
                (topic_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_recent_briefs(self, limit: int = 40, topic_id: Optional[int] = None) -> List[Dict[str, Any]]:
        capped_limit = max(1, min(limit, 200))
        with self._connect() as conn:
            if topic_id is not None:
                rows = conn.execute(
                    """
                    SELECT b.*, t.name AS topic_name
                    FROM briefs b
                    JOIN topics t ON t.id = b.topic_id
                    WHERE b.topic_id = ?
                    ORDER BY b.created_at DESC
                    LIMIT ?
                    """,
                    (topic_id, capped_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT b.*, t.name AS topic_name
                    FROM briefs b
                    JOIN topics t ON t.id = b.topic_id
                    ORDER BY b.created_at DESC
                    LIMIT ?
                    """,
                    (capped_limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_articles_by_date(self, topic_id: int, date_str: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE topic_id = ?
                  AND (DATE(published_at) = ? OR (published_at IS NULL AND DATE(created_at) = ?))
                ORDER BY published_at DESC, created_at DESC
                """,
                (topic_id, date_str, date_str),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_research_run(self, run_id: str, query: str, status: str,
                          report_path: Optional[str] = None,
                          report_content: Optional[str] = None,
                          started_at: Optional[str] = None,
                          finished_at: Optional[str] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_runs
                (run_id, query, status, report_path, report_content, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, query, status, report_path, report_content, started_at, finished_at),
            )

    def list_research_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, query, status, report_path, started_at, finished_at
                FROM research_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_research_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_topic(self, topic_id: int, fields: Dict[str, Any]) -> None:
        json_fields = {"keywords", "rss_sources", "push_channels"}
        updates = []
        params = []
        for key, value in fields.items():
            if key == "is_active":
                updates.append("is_active = ?")
                params.append(1 if value else 0)
            elif key in json_fields:
                updates.append(f"{key} = ?")
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            return
        params.append(topic_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE topics SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def cleanup_old_articles(self, days: int = 30) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE created_at < ?",
                (cutoff,),
            )
            return cursor.rowcount

    def get_app_config(self) -> Dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM app_config").fetchall()
        config: Dict[str, Any] = {}
        for row in rows:
            raw = row["value"]
            try:
                config[row["key"]] = json.loads(raw)
            except Exception:
                config[row["key"]] = raw
        return config

    def upsert_app_config(self, fields: Dict[str, Any]) -> None:
        if not fields:
            return
        with self._connect() as conn:
            for key, value in fields.items():
                conn.execute(
                    """
                    INSERT INTO app_config (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                      value = excluded.value,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, json.dumps(value, ensure_ascii=False)),
                )

    # ---------- Source reputation ----------
    def update_source_reputation(self, topic_id: int, source_domain: str, delta: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_reputation (topic_id, source_domain, score, vote_count, updated_at)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(topic_id, source_domain) DO UPDATE SET
                  score = source_reputation.score + excluded.score,
                  vote_count = source_reputation.vote_count + 1,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (topic_id, source_domain, delta),
            )

    def get_source_reputations(self, topic_id: int) -> Dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_domain, score FROM source_reputation WHERE topic_id = ?",
                (topic_id,),
            ).fetchall()
        return {row["source_domain"]: float(row["score"]) for row in rows}

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
