"""Pure helper utilities for Discord bot command handling."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple


def resolve_topic_reference(topic_ref: str, topics: Iterable[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Resolve a /brief topic reference from either numeric id or fuzzy name."""
    raw = (topic_ref or "").strip()
    topic_list = list(topics or [])
    if not raw:
        return None, "Topic is required."

    if raw.isdigit():
        topic_id = int(raw)
        for topic in topic_list:
            if int(topic.get("id", -1)) == topic_id:
                return topic, None
        return None, "Topic not found. Run /topics to inspect available IDs and names."

    lowered = raw.lower()
    matches = [topic for topic in topic_list if lowered in str(topic.get("name", "")).lower()]
    if not matches:
        return None, "Topic not found. Run /topics to inspect available IDs and names."
    if len(matches) > 1:
        options = ", ".join(f"{topic.get('id')} | {topic.get('name')}" for topic in matches[:5])
        return None, f"Multiple topics matched: {options}"
    return matches[0], None

