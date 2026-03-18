"""Pure helper utilities for Discord bot command handling."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


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


def parse_admin_ids(raw: str) -> Set[int]:
    values: Set[int] = set()
    for token in (raw or "").split(","):
        token = token.strip()
        if token.isdigit():
            values.add(int(token))
    return values


def is_discord_admin(user_id: int, raw_admin_ids: str) -> bool:
    return int(user_id) in parse_admin_ids(raw_admin_ids)


def build_topic_autocomplete_matches(
    current: str,
    topics: Iterable[Dict[str, Any]],
    limit: int = 25,
) -> List[Tuple[str, str]]:
    """Build autocomplete pairs of (display_name, value) for topic-like arguments."""
    topic_list = list(topics or [])
    query = (current or "").strip().lower()

    def score(topic: Dict[str, Any]) -> Tuple[int, str]:
        topic_id = str(topic.get("id", ""))
        name = str(topic.get("name", ""))
        lowered = name.lower()
        if not query:
            return (0, lowered)
        if topic_id == query:
            return (0, lowered)
        if lowered == query:
            return (1, lowered)
        if lowered.startswith(query):
            return (2, lowered)
        if query in lowered:
            return (3, lowered)
        if topic_id.startswith(query):
            return (4, lowered)
        return (99, lowered)

    filtered = [topic for topic in topic_list if score(topic)[0] < 99]
    if not query:
        filtered = topic_list
    filtered.sort(key=score)

    matches: List[Tuple[str, str]] = []
    for topic in filtered[:limit]:
        topic_id = str(topic.get("id", ""))
        name = str(topic.get("name", ""))
        matches.append((f"{topic_id} | {name}", name))
    return matches


def build_research_payload(query: str, language: str, brief_id: Optional[int] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"query": query, "language": language}
    if brief_id is not None:
        payload["brief_id"] = int(brief_id)
    return payload


def build_ask_payload(
    question: str,
    language: str,
    *,
    topic_id: Optional[int] = None,
    brief_id: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"message": question, "language": language}
    if topic_id is not None:
        payload["topic_id"] = int(topic_id)
    if brief_id is not None:
        payload["brief_id"] = int(brief_id)
    return payload


def build_analyze_payload(product: str, language: str, brief_id: Optional[int] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"product": product, "language": language}
    if brief_id is not None:
        payload["brief_id"] = int(brief_id)
    return payload
