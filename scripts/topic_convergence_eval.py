"""Offline topic convergence evaluator for ArcBrief.

Usage:
  python scripts/topic_convergence_eval.py --db arcbrief.db --threshold 0.6 --sample 20
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass
class ArticleRow:
    id: int
    topic_id: int
    title: str
    content: str
    published_at: str
    created_at: str


def _to_date(ts: str) -> str:
    raw = (ts or "").strip()
    if not raw:
        return "unknown"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return raw[:10] if len(raw) >= 10 else "unknown"


def _english_tokens(text: str) -> List[str]:
    lowered = (text or "").lower()
    return re.findall(r"[a-z0-9]+", lowered)


def _cjk_bigrams(text: str) -> List[str]:
    chars = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text or "")
    if len(chars) < 2:
        return chars
    return ["".join(chars[i : i + 2]) for i in range(len(chars) - 1)]


def event_fingerprint(title: str, content: str) -> Set[str]:
    base = f"{title or ''} {content or ''}"
    tokens = _english_tokens(base)
    bigrams = _cjk_bigrams(base)
    return set(tokens + bigrams)


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_articles(db_path: Path) -> List[ArticleRow]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, topic_id, title, COALESCE(content, '') AS content,
                   COALESCE(published_at, '') AS published_at,
                   COALESCE(created_at, '') AS created_at
            FROM articles
            ORDER BY topic_id, created_at DESC
            """
        ).fetchall()
        return [
            ArticleRow(
                id=int(r["id"]),
                topic_id=int(r["topic_id"]),
                title=str(r["title"] or ""),
                content=str(r["content"] or ""),
                published_at=str(r["published_at"] or ""),
                created_at=str(r["created_at"] or ""),
            )
            for r in rows
        ]
    finally:
        conn.close()


def cluster_group(items: List[ArticleRow], threshold: float) -> Tuple[int, List[Dict[str, object]]]:
    clusters: List[Dict[str, object]] = []
    for row in items:
        fp = event_fingerprint(row.title, row.content)
        assigned = False
        for cluster in clusters:
            score = jaccard(fp, cluster["fingerprint"])
            if score >= threshold:
                cluster["items"].append(row)
                # Keep a stable, conservative cluster signature (union improves recall).
                cluster["fingerprint"] = set(cluster["fingerprint"]) | fp
                assigned = True
                break
        if not assigned:
            clusters.append({"fingerprint": fp, "items": [row]})

    sample = []
    for c in clusters:
        members: List[ArticleRow] = c["items"]
        if len(members) <= 1:
            continue
        sample.append(
            {
                "size": len(members),
                "article_ids": [m.id for m in members[:6]],
                "titles": [m.title[:120] for m in members[:3]],
            }
        )
    return len(clusters), sample


def evaluate(rows: List[ArticleRow], threshold: float, sample_size: int) -> Dict[str, object]:
    grouped: Dict[Tuple[int, str], List[ArticleRow]] = {}
    for row in rows:
        day = _to_date(row.published_at or row.created_at)
        grouped.setdefault((row.topic_id, day), []).append(row)

    total_before = 0
    total_after = 0
    sampled_clusters: List[Dict[str, object]] = []

    for (_topic_id, _day), items in grouped.items():
        total_before += len(items)
        cluster_count, sample = cluster_group(items, threshold)
        total_after += cluster_count
        if sample:
            sampled_clusters.extend(sample)

    sampled_clusters.sort(key=lambda x: int(x.get("size", 0)), reverse=True)
    sampled_clusters = sampled_clusters[: max(1, sample_size)]

    duplicate_reduction = 0.0
    if total_before > 0:
        duplicate_reduction = 1 - (total_after / total_before)

    return {
        "threshold": threshold,
        "total_articles_before": total_before,
        "total_events_after": total_after,
        "duplicate_reduction_ratio": round(duplicate_reduction, 4),
        "sampled_merged_events": sampled_clusters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate topic convergence with event fingerprints")
    parser.add_argument("--db", default="arcbrief.db", help="Path to sqlite database")
    parser.add_argument("--threshold", type=float, default=0.6, help="Jaccard threshold (default: 0.6)")
    parser.add_argument("--sample", type=int, default=20, help="Number of sampled merged clusters")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    rows = load_articles(db_path)
    report = evaluate(rows, threshold=max(0.0, min(1.0, args.threshold)), sample_size=max(1, args.sample))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
