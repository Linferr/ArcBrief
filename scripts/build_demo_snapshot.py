"""Export read-only API responses to a static snapshot for the hosted demo.

Usage:
    python scripts/build_demo_snapshot.py --db arcbrief.db --out frontend/demo-data
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXCLUDED_GATE_DECISIONS = {"REJECT", "REVISE"}


def _json_response(client, path: str, params: Dict[str, Any] | None = None) -> Any:
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def _is_curated_run(run: Dict[str, Any]) -> bool:
    return (
        run.get("status") == "done"
        and str(run.get("delivery_status") or "full") != "limited"
        and str(run.get("gate_decision") or "").upper() not in EXCLUDED_GATE_DECISIONS
    )


def _article_dates(db_path: Path) -> List[tuple[int, str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT topic_id, DATE(COALESCE(published_at, created_at)) AS day
            FROM articles
            WHERE COALESCE(published_at, created_at) IS NOT NULL
            ORDER BY topic_id, day
            """
        ).fetchall()
    finally:
        conn.close()
    return [(int(topic_id), str(day)) for topic_id, day in rows if day]


def build_snapshot(db_path: Path) -> Dict[str, Any]:
    os.environ["ARCBRIEF_DB_PATH"] = str(db_path)
    os.environ["ARCBRIEF_DISABLE_AUTH"] = "1"

    from fastapi.testclient import TestClient
    import backend.main as main

    main.DB = main.ArcBriefDB(str(db_path))
    client = TestClient(main.app)

    topics = _json_response(client, "/api/topics")
    recent = _json_response(client, "/api/briefs/recent", {"limit": 200})
    briefs = recent.get("items") or []

    brief_history: Dict[str, List[Dict[str, Any]]] = {}
    for topic in topics:
        topic_id = topic["id"]
        brief_history[str(topic_id)] = _json_response(
            client,
            f"/api/briefs/{topic_id}/history",
            {"limit": 30, "since_hours": 0},
        )

    articles_by_date: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for topic_id, day in _article_dates(db_path):
        payload = _json_response(
            client,
            f"/api/topics/{topic_id}/articles",
            {"date": day, "sort": "time"},
        )
        articles_by_date.setdefault(str(topic_id), {})[day] = payload.get("articles") or []

    history_payload = _json_response(client, "/api/history", {"page": 1, "size": 50})
    curated_runs = [run for run in history_payload.get("results") or [] if _is_curated_run(run)]
    for run in curated_runs:
        # Local filesystem paths are not needed by the UI and should not be published.
        run["report_path"] = None

    reports: Dict[str, str] = {}
    for run in curated_runs:
        response = client.get(f"/api/report/{run['run_id']}")
        if response.status_code == 200 and response.text.strip():
            reports[run["run_id"]] = response.text
    curated_runs = [run for run in curated_runs if run["run_id"] in reports]

    history = {
        "total": len(curated_runs),
        "page": 1,
        "size": 50,
        "results": curated_runs,
    }

    feedback: Dict[str, Dict[str, int]] = {}
    for brief in briefs:
        stats = _json_response(client, f"/api/briefs/{brief['id']}/feedback")
        feedback[str(brief["id"])] = {
            "upvotes": int(stats.get("upvotes") or 0),
            "downvotes": int(stats.get("downvotes") or 0),
        }

    starter_packs = _json_response(client, "/api/starter-packs")
    config = _json_response(client, "/api/config")
    config["entity_watchlist"] = ""
    rss_health = _json_response(client, "/api/rss-health")

    generated_at = datetime.now().replace(microsecond=0).isoformat()
    system_status = {
        "started_at": generated_at,
        "scheduler_running": False,
        "active_research": 0,
        "max_concurrent_research": 3,
        "active_chat": 0,
        "max_concurrent_chat": 3,
        "max_reflections": 2,
        "rate_limit_backend": "static",
        "rate_limit_per_min": 60,
        "public_rate_limit_per_min": 15,
        "public_read_rate_limit_per_min": 60,
        "public_export_rate_limit_per_min": 10,
        "run_route_limit_per_min": 4,
        "chat_route_limit_per_min": 8,
        "search_provider_configured": "Static demo",
        "search_provider_effective": "Static demo",
        "search_provider_fallback": "Live search is disabled in the static demo.",
        "search_llm_assisted": False,
        "jobs": [],
    }

    return {
        "generated_at": generated_at,
        "topics": topics,
        "briefs_recent": {"count": len(briefs), "items": briefs},
        "brief_history": brief_history,
        "articles_by_date": articles_by_date,
        "history": history,
        "reports": reports,
        "feedback": feedback,
        "starter_packs": starter_packs,
        "config": config,
        "rss_health": rss_health,
        "system_status": system_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ArcBrief static demo snapshot.")
    parser.add_argument("--db", default=str(ROOT / "arcbrief.db"), help="Path to arcbrief.db")
    parser.add_argument("--out", default=str(ROOT / "frontend" / "demo-data"), help="Output directory")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    snapshot = build_snapshot(db_path)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "snapshot.json"
    out_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_file} ({out_file.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"Topics: {len(snapshot['topics'])}")
    print(f"Briefs: {snapshot['briefs_recent']['count']}")
    print(f"Reports: {len(snapshot['reports'])}")
    print(f"Article dates: {sum(len(days) for days in snapshot['articles_by_date'].values())}")


if __name__ == "__main__":
    main()
