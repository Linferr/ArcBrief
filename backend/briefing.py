"""Briefing generation (keyword clustering + config-driven behavior)."""

from __future__ import annotations

from datetime import datetime
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple
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

# Per-topic synthesis personas: injected into system prompt to focus the LLM's angle.
_TOPIC_SYNTHESIS_PERSONAS: Dict[str, str] = {
    "AI Daily": "Emphasize: model capability changes, product launches, and benchmark results.",
    "AI Policy & Safety": "Emphasize: regulatory actions, legal precedents, and policy actors and their positions.",
    "AI Builder Signals": "Emphasize: developer tooling changes, API updates, framework shifts, and workflow improvements.",
    "Global Trending": "Emphasize: geopolitical cause-effect chains, key actor motivations, and timeline of events.",
    "Macro and Metals": "Emphasize: price movements, central bank actions, macro indicators (CPI/yield/DXY), and market implications.",
}

_NOISY_SUMMARY_PATTERNS = [
    r"article\s+url\s*:",
    r"comments?\s+url\s*:",
    r"points?\s*:\s*\d+",
    r"#\s*comments?\s*:\s*\d+",
    r"\[\s*publishedat\s*\]",
    r"feed\s+did\s+not\s+provide\s+article\s+body\.?",
    r"source\s+body\s+is\s+unavailable;?\s*summary\s+uses\s+headline[-\s]level\s+evidence\.?",
]

_SOURCE_TIER_DOMAINS: Dict[str, str] = {
    # official / first-party
    "openai.com": "official",
    "anthropic.com": "official",
    "ai.meta.com": "official",
    "research.google": "official",
    "blog.research.google": "official",
    "blog.google": "official",
    "deepmind.google": "official",
    "huggingface.co": "official",
    # high-signal media
    "technologyreview.com": "high",
    "wired.com": "high",
    "techcrunch.com": "high",
    "arstechnica.com": "high",
    "theverge.com": "high",
    "venturebeat.com": "high",
    "foreignaffairs.com": "high",
    "wsj.com": "high",
    "feeds.a.dj.com": "high",
    "cnbc.com": "high",
    "npr.org": "high",
    "theguardian.com": "high",
    "bbc.co.uk": "high",
    "aljazeera.com": "high",
    "federalreserve.gov": "high",
    "marketwatch.com": "high",
    # medium aggregators
    "hnrss.org": "medium",
    "news.ycombinator.com": "medium",
    "marktechpost.com": "medium",
    "scmp.com": "medium",
    "mining.com": "medium",
    "news.google.com": "medium",
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
        # Fall back to title only; avoid injecting noisy boilerplate into summaries/cards.
        return title
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


def _normalize_synthesis_brief(item: Dict[str, Any], fallback_tag: str) -> Dict[str, Any]:
    topic_tag = (item.get("topic_tag") or fallback_tag).strip()
    headline = _truncate_words(item.get("headline") or "Daily executive summary", 15)
    summary = _truncate_words(item.get("summary") or "No synthesis provided.", 260)

    takeaways = item.get("key_takeaways") if isinstance(item.get("key_takeaways"), list) else []
    normalized_takeaways = [_truncate_words(str(t), 28) for t in takeaways if str(t).strip()]
    while len(normalized_takeaways) < 5:
        normalized_takeaways.append("Additional signal pending validation.")
    normalized_takeaways = normalized_takeaways[:12]

    sentiment = str(item.get("sentiment") or "neutral").strip().lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"

    reliability = str(item.get("reliability_score") or "med").strip().lower()
    if reliability not in {"high", "med", "low"}:
        reliability = "med"

    evidence_refs_raw = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
    evidence_refs: List[str] = []
    for ref in evidence_refs_raw:
        token = str(ref).strip()
        if token and token not in evidence_refs:
            evidence_refs.append(token)
    evidence_refs = evidence_refs[:12]

    return {
        "topic_tag": topic_tag,
        "headline": headline,
        "summary": summary,
        "key_takeaways": normalized_takeaways,
        "sentiment": sentiment,
        "reliability_score": reliability,
        "evidence_refs": evidence_refs,
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

    topic_persona = cfg.get("topic_persona", "")
    if topic_persona:
        instructions.append(f"TOPIC FOCUS: {topic_persona}")

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


def _fallback_synthesis_from_clusters(cluster_briefs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not cluster_briefs:
        return {
            "topic_tag": "Daily Executive Summary",
            "headline": "No synthesis available",
            "summary": "No high-signal synthesis could be generated.",
            "key_takeaways": ["No data available.", "No data available."],
            "sentiment": "neutral",
            "reliability_score": "low",
        }

    first = cluster_briefs[0]
    second = cluster_briefs[1] if len(cluster_briefs) > 1 else None
    if second:
        headline = _truncate_words(
            f"{first.get('headline', 'Primary signal')} and {second.get('headline', 'secondary signal')}",
            15,
        )
        summary = (
            f"{first.get('summary', '')} Secondary signal: {second.get('summary', '')}"
        ).strip()
        takeaways = [
            (first.get("key_takeaways") or ["No additional verified signal."])[0],
            (second.get("key_takeaways") or ["No additional verified signal."])[0],
        ]
    else:
        headline = first.get("headline", "Today's Brief")
        summary = first.get("summary", "")
        takeaways = first.get("key_takeaways", ["No additional signal.", "No additional signal."])

    return _normalize_synthesis_brief(
        {
            "topic_tag": "Daily Executive Summary",
            "headline": headline,
            "summary": summary,
            "key_takeaways": takeaways,
            "sentiment": "neutral",
            "reliability_score": first.get("reliability_score", "med"),
            "evidence_refs": [],
        },
        fallback_tag="Daily Executive Summary",
    )


def _fallback_synthesis_from_evidence(
    cluster_evidence: List[Dict[str, Any]],
    cluster_briefs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    snippets: List[Dict[str, str]] = []
    for cluster in cluster_evidence:
        for item in cluster.get("snippets", []):
            if isinstance(item, dict):
                snippets.append(item)

    if not snippets:
        return _fallback_synthesis_from_clusters(cluster_briefs or [])

    top = snippets[: min(8, len(snippets))]
    head = top[0]
    headline = _truncate_words(head.get("title", "Daily executive summary"), 15)
    summary = _truncate_words(" ".join(s.get("snippet", "") for s in top), 180)
    takeaways = [_truncate_words(s.get("title", "Primary signal"), 28) for s in top[:8]]
    source = head.get("source", "")
    reliability = _reliability_from_domain(source)
    return _normalize_synthesis_brief(
        {
            "topic_tag": "Daily Executive Summary",
            "headline": headline,
            "summary": summary,
            "key_takeaways": takeaways,
            "sentiment": "neutral",
            "reliability_score": reliability,
            "evidence_refs": [s.get("ref", "") for s in top[:12]],
        },
        fallback_tag="Daily Executive Summary",
    )


def _build_synthesis_evidence(
    sorted_clusters: List[Tuple[str, List[Dict[str, Any]]]],
    source_weights: Optional[Dict[str, float]] = None,
    per_cluster: Optional[int] = None,
    max_total: int = 36,
) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    added = 0
    for c_idx, (label, items) in enumerate(sorted_clusters, start=1):
        if added >= max_total:
            break
        cluster_id = f"C{c_idx}"
        items_sorted = sorted(items, key=lambda x: _item_sort_key(x, source_weights), reverse=True)
        limit = len(items_sorted) if per_cluster is None else max(1, per_cluster)
        snippets: List[Dict[str, str]] = []
        for e_idx, item in enumerate(items_sorted[:limit], start=1):
            if added >= max_total:
                break
            source = _extract_domain(item.get("url") or item.get("source") or "unknown")
            ts = item.get("published_at") or item.get("created_at") or "unknown"
            snippets.append(
                {
                    "ref": f"{cluster_id}-E{e_idx}",
                    "title": _truncate_words(_clean_signal_text(item.get("title") or "Untitled"), 18),
                    "source": source,
                    "time": ts,
                    "snippet": _truncate_words(_pick_best_item_text(item, label), 48),
                    "url": item.get("url", ""),
                }
            )
            added += 1
        payload.append({"cluster_id": cluster_id, "label": label, "snippets": snippets})
    return payload


def _generate_synthesis(
    llm: LLMClient | MockLLM,
    cluster_briefs: List[Dict[str, Any]],
    cluster_evidence: List[Dict[str, Any]],
    total_articles: int,
    language: str = "English (US)",
    app_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate one global executive synthesis directly from article-level evidence."""
    if not cluster_evidence:
        return {
            "topic_tag": "Daily Executive Summary",
            "headline": "No evidence available for synthesis",
            "summary": "Insufficient evidence to generate a global synthesis.",
            "key_takeaways": ["No data available.", "No data available."],
            "sentiment": "neutral",
            "reliability_score": "low",
        }

    dynamic_instruction = _build_dynamic_instruction(app_config, language)

    # Build reliability map from cluster_briefs (index-aligned with cluster_evidence)
    reliability_map: Dict[str, str] = {}
    for i, cb in enumerate(cluster_briefs):
        cid = f"C{i + 1}"
        reliability_map[cid] = cb.get("reliability_score", "med")

    evidence_lines: List[str] = []
    valid_refs: set[str] = set()
    evidence_count = 0
    for cluster in cluster_evidence:
        cluster_id = cluster.get("cluster_id", "")
        label = cluster.get("label", "")
        snippets = cluster.get("snippets", [])
        if cluster_id and label:
            rel = reliability_map.get(cluster_id, "med")
            evidence_lines.append(f"{cluster_id} [{label}] (reliability: {rel})")
        for snippet in snippets:
            ref = str(snippet.get("ref", "")).strip()
            title = str(snippet.get("title", "")).strip()
            source = str(snippet.get("source", "")).strip()
            ts = str(snippet.get("time", "")).strip()
            body = str(snippet.get("snippet", "")).strip()
            if not ref:
                continue
            valid_refs.add(ref)
            evidence_count += 1
            evidence_lines.append(
                f"- {ref} | {title} | source={source} | time={ts} | body={body}"
            )

    system_prompt = (
        "You are an intelligence analyst producing a daily executive synthesis.\n"
        "Given article-level evidence snippets, produce ONE global synthesis that:\n"
        "1. Identifies the most significant theme across all clusters\n"
        "2. Connects related developments across different clusters\n"
        "3. Highlights what decision-makers should focus on today\n\n"
        f"[DYNAMIC INSTRUCTION]\n{dynamic_instruction}\n\n"
        "[RULES]\n"
        "1. Output ONLY valid JSON. No markdown, no conversational text.\n"
        "2. The summary must be 10-16 sentences (roughly 300-600 words) and grounded in evidence snippets.\n"
        "3. The headline must capture the day's single most important theme (max 15 words).\n"
        "4. key_takeaways must contain 6-10 concise bullets, each traceable to evidence.\n"
        "5. evidence_refs must include references from at least two different clusters when available.\n"
        "6. evidence_refs should cite at least 6 snippets when total evidence >= 12.\n"
        "7. Do NOT introduce claims or entities that do not appear in [EVIDENCE SNIPPETS].\n"
        "8. Clusters marked reliability=low contain unconfirmed claims — treat them with appropriate uncertainty and do not let them dominate the synthesis.\n\n"
        "[EXPECTED JSON SCHEMA]\n"
        "{\n"
        "  \"headline\": \"[Max 15 words]\",\n"
        "  \"summary\": \"[10-16 sentences connecting cross-cluster patterns]\",\n"
        "  \"key_takeaways\": [\"[Takeaway 1]\", \"[Takeaway 2]\", \"...\"] ,\n"
        "  \"evidence_refs\": [\"[e.g., C1-E1]\", \"[e.g., C2-E1]\"],\n"
        "  \"sentiment\": \"[positive/neutral/negative]\",\n"
        "  \"reliability_score\": \"[high/med/low]\"\n"
        "}"
    )
    user_prompt = (
        f"Today's brief covers {total_articles} articles. Evidence snippets provided: {evidence_count}.\n\n"
        "[EVIDENCE SNIPPETS]\n"
        + "\n".join(evidence_lines)
    )

    try:
        raw = llm.invoke(system_prompt, user_prompt)
        parsed_text = _extract_json_text(raw)
        data = json.loads(parsed_text)
        if not isinstance(data, dict):
            raise ValueError("Not a dict")
    except Exception:
        return _fallback_synthesis_from_evidence(cluster_evidence, cluster_briefs)

    refs = data.get("evidence_refs") if isinstance(data.get("evidence_refs"), list) else []
    covered_clusters = {
        ref.split("-")[0]
        for ref in refs
        if isinstance(ref, str) and ref in valid_refs and "-" in ref
    }
    valid_ref_count = sum(1 for ref in refs if isinstance(ref, str) and ref in valid_refs)
    min_required_clusters = min(2, len(cluster_evidence))
    min_required_refs = 6 if evidence_count >= 12 else (3 if evidence_count >= 6 else 1)
    if min_required_clusters > 0 and len(covered_clusters) < min_required_clusters:
        return _fallback_synthesis_from_evidence(cluster_evidence, cluster_briefs)
    if valid_ref_count < min_required_refs:
        return _fallback_synthesis_from_evidence(cluster_evidence, cluster_briefs)

    return _normalize_synthesis_brief(
        {
            "topic_tag": "Daily Executive Summary",
            "headline": data.get("headline", "Today's Brief"),
            "summary": data.get("summary", ""),
            "key_takeaways": data.get("key_takeaways", []),
            "sentiment": data.get("sentiment", "neutral"),
            "reliability_score": data.get("reliability_score", "med"),
            "evidence_refs": refs,
        },
        fallback_tag="Daily Executive Summary",
    )


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


# Configurable freshness half-life: score = 0.5 when article age == halflife hours.
# Set ARCBRIEF_RECENCY_HALFLIFE_HOURS to adjust freshness sensitivity (default: 12h).
_RECENCY_HALFLIFE_HOURS: float = float(os.getenv("ARCBRIEF_RECENCY_HALFLIFE_HOURS", "12"))


def _time_recency_score(ts: str) -> float:
    """Return a 0..1 recency score using exponential decay (half-life = _RECENCY_HALFLIFE_HOURS)."""
    dt = _parse_timestamp(ts)
    if not dt:
        return 0.0
    now = datetime.utcnow()
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    age_seconds = max((now - dt).total_seconds(), 0.0)
    age_hours = age_seconds / 3600.0
    return math.exp(-age_hours * math.log(2) / _RECENCY_HALFLIFE_HOURS)


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


def _brief_locale(language: str) -> Dict[str, str]:
    if language == "Chinese (Simplified)":
        return {
            "doc_title": "每日简报",
            "core": "📌 今日核心 (TL;DR)",
            "clusters": "📂 专题速递",
            "insights": "💡 趋势与洞察",
            "sources": "来源索引",
            "summary_line": "一句话总结",
            "insight_trend": "趋势提炼",
            "insight_risk": "风险/机会",
            "empty": "暂无足够高质量素材，建议稍后重试。",
            "trend_default": "近期高信号信息主要集中在该主题的关键动作与落地执行。",
            "risk_default": "来源重叠可能带来盲区，建议继续补充一手社区证据。",
        }
    if language == "Japanese":
        return {
            "doc_title": "デイリーブリーフ",
            "core": "📌 今日の要点 (TL;DR)",
            "clusters": "📂 テーマ別クラスター",
            "insights": "💡 インサイト",
            "sources": "ソース索引",
            "summary_line": "一文要約",
            "insight_trend": "トレンド",
            "insight_risk": "リスク/機会",
            "empty": "十分な高品質ソースがありません。時間を置いて再実行してください。",
            "trend_default": "最近の高シグナル情報はこのテーマの実行可能な変化に集中しています。",
            "risk_default": "情報源の重複により盲点が生まれる可能性があります。",
        }
    return {
        "doc_title": "Daily Brief",
        "core": "📌 Core TL;DR",
        "clusters": "📂 Thematic Clusters",
        "insights": "💡 Insights",
        "sources": "Sources",
        "summary_line": "One-line summary",
        "insight_trend": "Trend",
        "insight_risk": "Risk/Opportunity",
        "empty": "Insufficient high-signal material. Please retry later.",
        "trend_default": "High-signal updates are concentrated on practical execution changes in this topic.",
        "risk_default": "Source overlap may hide dissenting evidence and edge-case failures.",
    }


def _ranked_unique_items(
    clusters: Dict[str, List[Dict[str, Any]]],
    source_weights: Optional[Dict[str, float]],
    limit: int = 36,
) -> List[Tuple[str, Dict[str, Any]]]:
    ranked: List[Tuple[str, Dict[str, Any]]] = []
    seen: set[str] = set()
    sorted_clusters = sorted(
        clusters.items(),
        key=lambda kv: _cluster_sort_key(kv[1], source_weights),
        reverse=True,
    )
    for label, items in sorted_clusters:
        for item in sorted(items, key=lambda x: _item_sort_key(x, source_weights), reverse=True):
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            dedupe_key = url or f"{label}:{title}"
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            ranked.append((label, item))
            if len(ranked) >= max(1, limit):
                return ranked
    return ranked


def _build_source_entries(
    ranked_items: List[Tuple[str, Dict[str, Any]]],
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    key_to_cid: Dict[str, str] = {}
    for idx, (_label, item) in enumerate(ranked_items, start=1):
        cid = f"C{idx}"
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "Untitled").strip()
        source = _extract_domain(item.get("source") or url or "")
        published = (item.get("published_at") or item.get("created_at") or "").strip()
        content = _pick_best_item_text(item, "source")
        entry = {
            "cid": cid,
            "title": title,
            "url": url,
            "source": source,
            "published_at": published,
            "content": _truncate_words(content, 120),
        }
        entries.append(entry)
        if url:
            key_to_cid[url] = cid
    return entries, key_to_cid


def _build_v3_system_prompt(language: str, app_config: Optional[Dict[str, Any]]) -> str:
    locale = _brief_locale(language)
    dynamic_instruction = _build_dynamic_instruction(app_config, language)
    return (
        "Role: You are a senior intelligence analyst with OSINT expertise. "
        "Transform fragmented updates into a dense, analytical brief.\n\n"
        "Core principles:\n"
        "1) Dynamic clustering: infer 3-4 key themes from source similarity; do not hardcode categories.\n"
        "2) High signal density: prefer entities, metrics, dates, actions, and consequences.\n"
        "3) Deduplication: merge repeated reporting of the same event, keep the most complete details.\n"
        "4) Attribution: every claim must cite source ids as (C1) or (C2, C5).\n"
        "5) Rendering: use concise bullets, bold key terms, and thematic emoji in cluster titles.\n"
        "6) Preserve source titles verbatim in original language. Do not translate source titles.\n"
        "7) CONFIDENCE: for significant claims backed by only one source, note [LOW CONFIDENCE]. "
        "For claims corroborated by 3+ sources, note [HIGH CONFIDENCE].\n"
        "8) CROSS-VERIFICATION: when sources conflict, present both positions explicitly: "
        "\"(C1) asserts X, while (C3) argues Y.\"\n"
        "9) FIRST PRINCIPLES: in Insights, identify root causes and second-order effects, not just surface events.\n"
        "10) STAKEHOLDER: note who benefits and who is disadvantaged by the developments.\n"
        "11) CONTRARIAN: each cluster should mention at least one risk, limitation, or opposing view if evidence exists.\n\n"
        "Banned words (never use): groundbreaking, revolutionary, game-changing, cutting-edge, "
        "paradigm shift, transformative, unprecedented. Use precise, measured language.\n\n"
        f"{dynamic_instruction}\n\n"
        "Output format (strict markdown):\n"
        f"## {locale['core']}\n"
        f"> **{locale['summary_line']}**: [<= 80 words summary with impact] (C#)\n\n"
        f"## {locale['clusters']}\n"
        "### [Emoji] [Auto-generated cluster title]\n"
        "- **[Key actor/action]**: ... (C#)\n"
        "- **[Data/details]**: ... (C#)\n\n"
        f"## {locale['insights']}\n"
        f"- **{locale['insight_trend']}**: ... (C#)\n"
        f"- **{locale['insight_risk']}**: ... (C#)\n\n"
        "Return markdown only."
    )


def _build_v3_fallback_markdown(
    topic_name: str,
    ranked_items: List[Tuple[str, Dict[str, Any]]],
    source_entries: List[Dict[str, str]],
    source_ref_map: Dict[str, str],
    language: str,
) -> str:
    locale = _brief_locale(language)
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines: List[str] = [f"# {date_str} {topic_name} {locale['doc_title']}", ""]

    if not ranked_items:
        lines.append(f"## {locale['core']}")
        lines.append("")
        lines.append(f"> **{locale['summary_line']}**: {locale['empty']}")
        lines.append("")
        lines.append(f"## {locale['sources']}")
        lines.append("")
        lines.append("- (C0) No source items collected.")
        return "\n".join(lines).strip() + "\n"

    lines.append(f"## {locale['core']}")
    lines.append("")
    top_title = (ranked_items[0][1].get("title") or "").strip() or topic_name
    top_url = (ranked_items[0][1].get("url") or "").strip()
    top_ref = source_ref_map.get(top_url, "C1")
    lines.append(f"> **{locale['summary_line']}**: **{top_title}** ({top_ref})")
    lines.append("")

    lines.append(f"## {locale['clusters']}")
    lines.append("")
    clusters: Dict[str, List[Dict[str, Any]]] = {}
    for label, item in ranked_items:
        clusters.setdefault(label or "General", []).append(item)
    emoji_pool = ["🚀", "💼", "⚖️", "🧪", "🌐", "📈"]
    for idx, (label, items) in enumerate(list(clusters.items())[:4]):
        emoji = emoji_pool[idx % len(emoji_pool)]
        lines.append(f"### {emoji} {label}")
        for item in items[:2]:
            title = (item.get("title") or "Untitled").strip()
            body = _truncate_words(_pick_best_item_text(item, label), 50)
            url = (item.get("url") or "").strip()
            ref = source_ref_map.get(url, "C1")
            lines.append(f"- **{title}**: {body} ({ref})")
            lines.append("")

    lines.append(f"## {locale['insights']}")
    lines.append("")
    lines.append(f"- **{locale['insight_trend']}**: {locale['trend_default']} (C1)")
    lines.append("")
    lines.append(f"- **{locale['insight_risk']}**: {locale['risk_default']} (C1)")
    lines.append("")

    lines.append(f"## {locale['sources']}")
    lines.append("")
    for entry in source_entries[:20]:
        url = entry.get("url") or ""
        source_suffix = f" [{entry['source']}]" if entry.get("source") else ""
        date_suffix = f" ({entry['published_at'][:10]})" if entry.get("published_at") else ""
        if url:
            lines.append(f"- ({entry['cid']}) {entry['title']}{source_suffix}{date_suffix} - {url}")
        else:
            lines.append(f"- ({entry['cid']}) {entry['title']}{source_suffix}{date_suffix}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _ensure_sources_section(markdown_text: str, source_entries: List[Dict[str, str]], language: str) -> str:
    locale = _brief_locale(language)
    text = (markdown_text or "").strip()
    if not text:
        text = ""
    if f"## {locale['sources']}" in text:
        return text + ("\n" if not text.endswith("\n") else "")
    lines = [text, "", f"## {locale['sources']}", ""]
    for entry in source_entries[:20]:
        url = entry.get("url") or ""
        if url:
            lines.append(f"- ({entry['cid']}) {entry['title']} - {url}")
        else:
            lines.append(f"- ({entry['cid']}) {entry['title']}")
    lines.append("")
    return "\n".join([line for line in lines if line is not None]).strip() + "\n"


def generate_brief_markdown(
    topic_name: str,
    clusters: Dict[str, List[Dict[str, Any]]],
    source_weights: Optional[Dict[str, float]] = None,
    language: str = "English (US)",
    app_config: Optional[Dict[str, Any]] = None,
) -> str:
    language_used = language if language in _LANGUAGE_OUTPUT_HINTS else "English (US)"
    ranked_items = _ranked_unique_items(clusters, source_weights, limit=32)
    source_entries, source_ref_map = _build_source_entries(ranked_items)

    llm = _get_llm()
    if llm and ranked_items:
        system_prompt = _build_v3_system_prompt(language_used, app_config=app_config)
        payload = {
            "topic_context": topic_name,
            "raw_articles_content": [
                {
                    "source_id": entry["cid"],
                    "title": entry["title"],
                    "url": entry["url"],
                    "source": entry["source"],
                    "published_at": entry["published_at"],
                    "content": entry["content"],
                }
                for entry in source_entries
            ],
            "source_map": [
                {
                    "id": entry["cid"],
                    "title": entry["title"],
                    "url": entry["url"],
                }
                for entry in source_entries
            ],
        }
        try:
            raw = llm.invoke(system_prompt, json.dumps(payload, ensure_ascii=False))
            rendered = (raw or "").strip()
            if rendered and "##" in rendered:
                return _ensure_sources_section(rendered, source_entries, language_used)
        except Exception:
            pass

    return _build_v3_fallback_markdown(
        topic_name,
        ranked_items,
        source_entries,
        source_ref_map,
        language_used,
    )


def build_brief_for_topic(
    topic: Any,
    items: List[Dict[str, Any]],
    source_weights: Optional[Dict[str, float]] = None,
    app_config: Optional[Dict[str, Any]] = None,
) -> str:
    cfg = dict(app_config or {})

    if cfg.get("strict_academic_mode", False):
        items = _filter_social_media(items)

    # Inject topic-specific synthesis persona based on topic name
    persona = _TOPIC_SYNTHESIS_PERSONAS.get(topic.name, "")
    if persona and "topic_persona" not in cfg:
        cfg["topic_persona"] = persona

    watchlist_raw = cfg.get("entity_watchlist", "")
    watchlist = [w.strip() for w in watchlist_raw.split(",") if w.strip()] if watchlist_raw else []
    language = cfg.get("report_language", "English (US)")
    if language not in _LANGUAGE_OUTPUT_HINTS:
        language = "English (US)"

    clusters = cluster_by_keywords(items, topic.keywords, watchlist=watchlist)
    return generate_brief_markdown(
        topic.name,
        clusters,
        source_weights=source_weights,
        language=language,
        app_config=cfg,
    )


def llm_chat(system_prompt: str, user_prompt: str) -> Optional[str]:
    """One-shot LLM completion for use outside the briefing pipeline (e.g. /api/chat)."""
    llm = _get_llm()
    if llm is None:
        return None
    try:
        return llm.invoke(system_prompt, user_prompt)
    except Exception:
        return None
