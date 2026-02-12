"""Briefing generation (keyword clustering + config-driven behavior)."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from foreign_query_agent.config import Settings
from foreign_query_agent.llm import LLMClient, LLMConfig, MockLLM


_SOCIAL_MEDIA_DOMAINS = frozenset(
    {
        "twitter.com",
        "x.com",
        "reddit.com",
        "facebook.com",
        "tiktok.com",
        "instagram.com",
        "threads.net",
        "weibo.com",
        "t.co",
    }
)


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or url
        return host.replace("www.", "").lower()
    except Exception:
        return url.lower()


def _is_social_media(url: str) -> bool:
    domain = _extract_domain(url)
    return any(domain == sm or domain.endswith(f".{sm}") for sm in _SOCIAL_MEDIA_DOMAINS)


def _filter_social_media(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove articles from social media sources (strict academic mode)."""
    return [
        item
        for item in items
        if not _is_social_media(item.get("source") or item.get("url") or "")
    ]


def cluster_by_keywords(
    items: List[Dict[str, Any]],
    keywords: List[str],
    watchlist: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Cluster items by keyword matching with score-based assignment.

    Each item is annotated with `_match_score` and `_match_in` (title/content/none)
    for downstream explainability. Watchlist entities get a +10 bonus when matched.
    """
    clusters: Dict[str, List[Dict[str, Any]]] = {}
    lowered = [k.lower() for k in keywords if k]
    watchlist_lower = [w.lower().strip() for w in (watchlist or []) if w.strip()]

    for item in items:
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()

        best_keyword = "other"
        best_score = 0
        best_in = "none"

        for kw in lowered:
            if not kw:
                continue
            title_hits = title.count(kw)
            content_hits = content.count(kw)
            score = title_hits * 3 + content_hits
            if score > best_score:
                best_score = score
                best_keyword = kw
                best_in = "title" if title_hits > 0 else ("content" if content_hits > 0 else "none")

        watchlist_bonus = 0
        for entity in watchlist_lower:
            if entity in title or entity in content:
                watchlist_bonus = max(watchlist_bonus, 10)
        best_score += watchlist_bonus

        enriched = {**item, "_match_score": best_score, "_match_in": best_in}
        clusters.setdefault(best_keyword, []).append(enriched)

    return clusters


def _get_llm() -> Optional[LLMClient | MockLLM]:
    settings = Settings()
    if settings.mock_mode:
        return MockLLM()
    if not settings.llm_api_key:
        return None
    try:
        cfg = LLMConfig(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        return LLMClient(cfg)
    except Exception:
        return None


_COGNITIVE_MODEL_INSTRUCTIONS: Dict[str, str] = {
    "Neutral (Fact-first)": (
        "Cognitive Model: Keep a neutral, fact-first stance. Avoid rhetorical language and keep interpretations minimal."
    ),
    "Critique-heavy (Skeptic)": (
        "Cognitive Model: Adopt a skeptic stance. Stress-test claims and highlight weak assumptions before accepting conclusions."
    ),
}


_LANGUAGE_OUTPUT_HINTS: Dict[str, str] = {
    "English (US)": "Write in English (US).",
    "Chinese (Simplified)": "Write in Simplified Chinese.",
    "Japanese": "Write in Japanese.",
}

_NOISY_SUMMARY_PATTERNS = [
    r"article\s+url\s*:",
    r"comments?\s+url\s*:",
    r"points?\s*:\s*\d+",
    r"#\s*comments?\s*:\s*\d+",
    r"\[\s*publishedat\s*\]",
]

_SOURCE_TIER_DOMAINS: Dict[str, str] = {
    # official / first-party
    "openai.com": "official",
    "anthropic.com": "official",
    "ai.meta.com": "official",
    "research.google": "official",
    "blog.research.google": "official",
    "blog.google": "official",
    "huggingface.co": "official",
    # high-signal media
    "technologyreview.com": "high",
    "wired.com": "high",
    "techcrunch.com": "high",
    "arstechnica.com": "high",
    "theverge.com": "high",
    "venturebeat.com": "high",
    # medium aggregators
    "hnrss.org": "medium",
    "news.ycombinator.com": "medium",
    "marktechpost.com": "medium",
    # low-noise scientific feed (valuable but noisy for daily brief)
    "arxiv.org": "low",
}

_SOURCE_TIER_SCORE: Dict[str, float] = {
    "official": 0.95,
    "high": 0.80,
    "medium": 0.65,
    "low": 0.45,
}


def _truncate_words(text: str, max_words: int) -> str:
    words = (text or "").strip().split()
    if not words:
        return ""
    return " ".join(words[:max_words]).strip()


def _clean_signal_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for pattern in _NOISY_SUMMARY_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_like_low_signal_text(text: str) -> bool:
    cleaned = _clean_signal_text(text)
    if len(cleaned) < 24:
        return True
    lowered = cleaned.lower()
    return any(re.search(pattern, lowered) for pattern in _NOISY_SUMMARY_PATTERNS)


def _pick_best_item_text(item: Dict[str, Any], label: str) -> str:
    content = _clean_signal_text(item.get("content") or "")
    title = _clean_signal_text(item.get("title") or f"{label} update")
    if content and not _looks_like_low_signal_text(content):
        return content
    if title:
        return f"{title}. Source body is unavailable; summary uses headline-level evidence."
    return "No high-signal content was available from the collected feed."


def _source_tier_from_domain(domain: str) -> str:
    normalized = (domain or "").strip().lower()
    if not normalized:
        return "medium"
    for known, tier in _SOURCE_TIER_DOMAINS.items():
        if normalized == known or normalized.endswith(f".{known}"):
            return tier
    return "medium"


def _source_tier_score(domain: str) -> float:
    tier = _source_tier_from_domain(domain)
    return _SOURCE_TIER_SCORE.get(tier, _SOURCE_TIER_SCORE["medium"])


def _reliability_from_domain(domain: str) -> str:
    tier = _source_tier_from_domain(domain)
    if tier in {"official", "high"}:
        return "high"
    if tier == "medium":
        return "med"
    return "low"


def _extract_json_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _normalize_structured_brief(item: Dict[str, Any], fallback_tag: str) -> Dict[str, Any]:
    topic_tag = (item.get("topic_tag") or fallback_tag).strip()
    headline = _truncate_words(item.get("headline") or "Untitled event", 15)
    summary = _truncate_words(item.get("summary") or "No summary provided.", 50)

    takeaways = item.get("key_takeaways") if isinstance(item.get("key_takeaways"), list) else []
    normalized_takeaways = [_truncate_words(str(t), 24) for t in takeaways if str(t).strip()]
    while len(normalized_takeaways) < 2:
        normalized_takeaways.append("No additional verified signal.")
    normalized_takeaways = normalized_takeaways[:2]

    sentiment = str(item.get("sentiment") or "neutral").strip().lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"

    reliability = str(item.get("reliability_score") or "med").strip().lower()
    if reliability not in {"high", "med", "low"}:
        reliability = "med"

    return {
        "topic_tag": topic_tag,
        "headline": headline,
        "summary": summary,
        "key_takeaways": normalized_takeaways,
        "sentiment": sentiment,
        "reliability_score": reliability,
    }


def _build_dynamic_instruction(app_config: Optional[Dict[str, Any]], language: str) -> str:
    cfg = app_config or {}
    instructions: List[str] = []

    if cfg.get("critical_analysis_layer", False):
        instructions.append(
            "Critical Analysis: Actively identify logical fallacies, missing context, or opposing viewpoints in the provided sources. "
            "Dedicate a specific subsection named '### Critical Vulnerabilities / Counter-arguments' to expose these flaws."
        )
    if cfg.get("strict_academic_mode", False):
        instructions.append(
            "Strict Verification: Only include claims backed by data, official legislation, or empirical evidence. "
            "Discard all speculative or opinion-based statements from the sources."
        )

    cognitive_model = cfg.get("cognitive_model", "Neutral (Fact-first)")
    instructions.append(
        _COGNITIVE_MODEL_INSTRUCTIONS.get(
            cognitive_model,
            _COGNITIVE_MODEL_INSTRUCTIONS["Neutral (Fact-first)"],
        )
    )
    instructions.append(_LANGUAGE_OUTPUT_HINTS.get(language, _LANGUAGE_OUTPUT_HINTS["English (US)"]))
    return "\n".join(instructions)


def _build_focus_entities_block(app_config: Optional[Dict[str, Any]]) -> str:
    cfg = app_config or {}
    watchlist_raw = (cfg.get("entity_watchlist") or "").strip()
    if not watchlist_raw:
        return ""
    watchlist = ", ".join([w.strip() for w in watchlist_raw.split(",") if w.strip()])
    if not watchlist:
        return ""
    return (
        "[FOCUS ENTITIES]\n"
        f"Prioritize extraction and analysis concerning the following entities: {watchlist}. "
        "Ensure their strategic movements are central to the report.\n\n"
    )


def _build_raw_news_block(items: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for item in items[:8]:
        title = (item.get("title") or "").strip()
        content = _pick_best_item_text(item, "news")
        source = _extract_domain(item.get("url") or item.get("source") or "unknown")
        source_tier = _source_tier_from_domain(source)
        published_at = item.get("published_at") or item.get("created_at") or "unknown"
        chunks.append(
            f"Title: {title}\n"
            f"Source: {source}\n"
            f"SourceTier: {source_tier}\n"
            f"Time: {published_at}\n"
            f"Body: {content[:360]}"
        )
    return "\n\n".join(chunks)


def _structured_fallback(label: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    first = items[0] if items else {}
    first_title = (first.get("title") or f"{label} update").strip()
    summary_source = _pick_best_item_text(first, label)
    first_domain = _extract_domain(first.get("url") or first.get("source") or "")
    reliability = _reliability_from_domain(first_domain)

    takeaways: List[str] = []
    for candidate in items[:2]:
        title = _clean_signal_text(candidate.get("title") or "")
        if title:
            takeaways.append(_truncate_words(title, 24))
    while len(takeaways) < 2:
        takeaways.append("Signal under review pending additional verified details.")

    return [
        _normalize_structured_brief(
            {
                "topic_tag": label,
                "headline": first_title,
                "summary": summary_source,
                "key_takeaways": takeaways[:2],
                "sentiment": "neutral",
                "reliability_score": reliability,
            },
            fallback_tag=label,
        )
    ]


def _summarize_cluster_with_llm(
    llm: LLMClient | MockLLM,
    label: str,
    items: List[Dict[str, Any]],
    language: str = "English (US)",
    app_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    dynamic_instruction = _build_dynamic_instruction(app_config, language)
    focus_block = _build_focus_entities_block(app_config)
    raw_news = _build_raw_news_block(items)
    system_prompt = (
        "You are an automated intelligence parser. Your task is to extract and summarize key news events "
        "from the provided raw text and output a strict JSON array.\n\n"
        "[RULES]\n"
        "1. Output ONLY valid JSON. No markdown formatting blocks (like ```json), no conversational text.\n"
        "2. The summary must be a single, information-dense paragraph.\n"
        "3. Extract exactly 2 bullet points for \"key_takeaways\".\n\n"
        "[DYNAMIC CRITIQUE INSTRUCTION]\n"
        f"{dynamic_instruction}\n\n"
        "[EXPECTED JSON SCHEMA]\n"
        "{\n"
        "  \"briefs\": [\n"
        "    {\n"
        "      \"topic_tag\": \"[e.g., AI Policy - EU Region]\",\n"
        "      \"headline\": \"[Max 15 words]\",\n"
        "      \"summary\": \"[Max 50 words, dense formulation]\",\n"
        "      \"key_takeaways\": [\"[Takeaway 1]\", \"[Takeaway 2]\"],\n"
        "      \"sentiment\": \"[positive/neutral/negative]\",\n"
        "      \"reliability_score\": \"[high/med/low based on source authority]\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    user_prompt = (
        f"{focus_block}"
        "[INPUT DATA]\n"
        "<raw_news>\n"
        f"{raw_news}\n"
        "</raw_news>"
    )

    raw = llm.invoke(system_prompt, user_prompt)
    parsed_text = _extract_json_text(raw)
    try:
        data = json.loads(parsed_text)
    except Exception:
        return _structured_fallback(label, items)

    if not isinstance(data, dict):
        return _structured_fallback(label, items)
    briefs = data.get("briefs")
    if not isinstance(briefs, list) or not briefs:
        return _structured_fallback(label, items)

    normalized = [
        _normalize_structured_brief(item, fallback_tag=label)
        for item in briefs
        if isinstance(item, dict)
    ]
    return normalized or _structured_fallback(label, items)


def _build_explainability(label: str, items: List[Dict[str, Any]]) -> List[str]:
    """Build a short explainability annotation for a cluster."""
    lines: List[str] = []

    src_counts: Dict[str, int] = {}
    for item in items:
        src = item.get("source", "") or "unknown"
        host = _extract_domain(src) if src != "unknown" else src
        src_counts[host] = src_counts.get(host, 0) + 1
    src_parts = [f"{k}: {v}" for k, v in sorted(src_counts.items(), key=lambda x: -x[1])[:5]]

    pub_count = sum(1 for i in items if i.get("published_at"))
    fallback_count = len(items) - pub_count

    title_match = sum(1 for i in items if i.get("_match_in") == "title")
    content_match = sum(1 for i in items if i.get("_match_in") == "content")
    no_match = len(items) - title_match - content_match

    match_parts = []
    if title_match:
        match_parts.append(f"title: {title_match}")
    if content_match:
        match_parts.append(f"content: {content_match}")
    if no_match:
        match_parts.append(f"other: {no_match}")

    lines.append(f"> **Why included** | keyword: `{label}` | match: {', '.join(match_parts)}")
    lines.append(f"> sources: {', '.join(src_parts)} | time: published_at({pub_count}) fallback({fallback_count})")
    return lines


def _parse_timestamp(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    raw = ts.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _time_recency_score(ts: str) -> float:
    """Return a 0..1 recency score, where newer timestamps score higher."""
    dt = _parse_timestamp(ts)
    if not dt:
        return 0.0
    now = datetime.utcnow()
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    age_seconds = max((now - dt).total_seconds(), 0.0)
    age_days = age_seconds / 86400.0
    return 1.0 / (1.0 + age_days)


def _normalize_reputation(raw_score: float) -> float:
    """Map raw reputation score into 0..1 for stable blending."""
    clipped = max(-5.0, min(5.0, raw_score))
    return (clipped + 5.0) / 10.0


def _cluster_sort_key(
    items: List[Dict[str, Any]],
    source_weights: Optional[Dict[str, float]] = None,
) -> float:
    """Hybrid sort key: 70% time recency + 30% average source reputation."""
    latest_ts = ""
    latest_dt: Optional[datetime] = None
    for item in items:
        ts = item.get("published_at") or item.get("created_at") or ""
        dt = _parse_timestamp(ts)
        if dt is None:
            continue
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
            latest_ts = ts
    time_score = _time_recency_score(latest_ts)

    rep_values: List[float] = []
    for item in items:
        src = item.get("url") or item.get("source") or ""
        domain = _extract_domain(src)
        tier_score = _source_tier_score(domain)
        if source_weights and domain in source_weights:
            dynamic_score = _normalize_reputation(source_weights.get(domain, 0.0))
            rep_values.append(dynamic_score * 0.6 + tier_score * 0.4)
        else:
            rep_values.append(tier_score)
    rep_score = sum(rep_values) / len(rep_values) if rep_values else 0.5

    return time_score * 0.7 + rep_score * 0.3


def _item_sort_key(
    item: Dict[str, Any],
    source_weights: Optional[Dict[str, float]] = None,
) -> float:
    """Sort key for individual items within a cluster."""
    ts = item.get("published_at") or item.get("created_at") or ""
    time_score = _time_recency_score(ts)

    src = item.get("url") or item.get("source") or ""
    domain = _extract_domain(src)
    tier_score = _source_tier_score(domain)
    rep_score = tier_score
    if source_weights and domain in source_weights:
        dynamic_score = _normalize_reputation(source_weights.get(domain, 0.0))
        rep_score = dynamic_score * 0.6 + tier_score * 0.4

    return time_score * 0.7 + rep_score * 0.3


def generate_brief_markdown(
    topic_name: str,
    clusters: Dict[str, List[Dict[str, Any]]],
    source_weights: Optional[Dict[str, float]] = None,
    language: str = "English (US)",
    app_config: Optional[Dict[str, Any]] = None,
) -> str:
    llm = _get_llm()
    date_str = datetime.now().strftime("%Y-%m-%d")

    total_items = sum(len(v) for v in clusters.values())
    source_counts: Dict[str, int] = {}
    for items in clusters.values():
        for item in items:
            source = item.get("source", "") or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

    source_line = " | ".join([f"{k}: {v}" for k, v in source_counts.items()]) if source_counts else "No source stats"

    lines = [
        f"# {date_str} {topic_name} Daily Brief",
        "",
        f"> Total: {total_items} articles",
        f"> Sources: {source_line}",
        "",
        "## TLDR",
        "",
    ]

    tldr_topics = list(clusters.keys())[:5]
    lines.append(" | ".join(tldr_topics) if tldr_topics else "No major topic")
    lines.append("")
    lines.append("---")
    lines.append("")

    sorted_clusters = sorted(
        clusters.items(),
        key=lambda kv: _cluster_sort_key(kv[1], source_weights),
        reverse=True,
    )

    for idx, (label, items) in enumerate(sorted_clusters, start=1):
        items_sorted = sorted(items, key=lambda x: _item_sort_key(x, source_weights), reverse=True)

        lines.append(f"## {idx}. {label}")
        lines.append("")
        if llm:
            try:
                briefs = _summarize_cluster_with_llm(
                    llm,
                    label,
                    items_sorted,
                    language=language,
                    app_config=app_config,
                )
            except Exception:
                briefs = _structured_fallback(label, items_sorted)
        else:
            briefs = _structured_fallback(label, items_sorted)

        for brief in briefs[:2]:
            lines.append(f"### {brief['topic_tag']}")
            lines.append(f"**{brief['headline']}**")
            lines.append("")
            lines.append(brief["summary"])
            lines.append("")
            lines.append("**Key Takeaways**")
            for takeaway in brief["key_takeaways"][:2]:
                lines.append(f"- {takeaway}")
            lines.append("")
            lines.append(
                f"*Sentiment: {brief['sentiment']} | Reliability: {brief['reliability_score']}*"
            )
            lines.append("")

        lines.append(f"*(Related articles: {len(items_sorted)})*")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Sources")
    lines.append("")
    seen_urls: set[str] = set()
    for items in clusters.values():
        for item in sorted(
            items,
            key=lambda x: x.get("published_at") or x.get("created_at") or "",
            reverse=True,
        ):
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = item.get("title", "Untitled")
            ts = item.get("published_at") or item.get("created_at") or ""
            ts_source = "published_at" if item.get("published_at") else "fallback(created_at)"
            source = item.get("source", "")
            ts_display = f" ({ts[:10]})" if ts else ""
            source_display = f" [{source}]" if source else ""
            time_source_display = f" [{ts_source}]"
            lines.append(f"- {title}{source_display}{ts_display}{time_source_display}")
            if len(seen_urls) >= 20:
                break
        if len(seen_urls) >= 20:
            break
    lines.append("")

    return "\n".join(lines)


def build_brief_for_topic(
    topic: Any,
    items: List[Dict[str, Any]],
    source_weights: Optional[Dict[str, float]] = None,
    app_config: Optional[Dict[str, Any]] = None,
) -> str:
    cfg = app_config or {}

    if cfg.get("strict_academic_mode", False):
        items = _filter_social_media(items)

    watchlist_raw = cfg.get("entity_watchlist", "")
    watchlist = [w.strip() for w in watchlist_raw.split(",") if w.strip()] if watchlist_raw else []
    language = cfg.get("report_language", "English (US)")

    clusters = cluster_by_keywords(items, topic.keywords, watchlist=watchlist)
    return generate_brief_markdown(
        topic.name,
        clusters,
        source_weights=source_weights,
        language=language,
        app_config=cfg,
    )


