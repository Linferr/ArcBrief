"""Briefing generation (Phase 1 keyword clustering)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from foreign_query_agent.config import Settings
from foreign_query_agent.llm import LLMClient, LLMConfig, MockLLM


def cluster_by_keywords(items: List[Dict[str, str]], keywords: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """Cluster items by keyword matching with score-based assignment."""
    clusters: Dict[str, List[Dict[str, str]]] = {}
    lowered = [k.lower() for k in keywords if k]

    for item in items:
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()

        # Score each keyword (best match wins)
        best_keyword = "其他"
        best_score = 0

        for kw in lowered:
            if not kw:
                continue
            # Count occurrences (title match weighted 3x)
            score = title.count(kw) * 3 + content.count(kw)
            if score > best_score:
                best_score = score
                best_keyword = kw

        clusters.setdefault(best_keyword, []).append(item)

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


def _summarize_cluster_with_llm(llm, label: str, items: List[Dict[str, str]]) -> str:
    titles = "\n".join([f"- {i.get('title','')[:120]}" for i in items[:8]])
    snippets = "\n".join([
        f"- {i.get('content','')[:220]}" for i in items[:4] if i.get("content")
    ])

    system_prompt = """You are a concise analyst. Summarize news into clean Chinese briefing text.

CRITICAL RULES:
- NO URLs or links in output
- Use proper Chinese punctuation (。、）
- Output ONLY the summary, no meta-text
- Keep summaries factual and objective"""

    user_prompt = f"""主题：{label}

标题：
{titles}

内容：
{snippets}

输出要求：
1. 2-3句核心摘要（不含URL、不含"根据报道"等冗余词）
2. 2-4个要点（使用"- "开头）
3. 仅输出摘要内容，不要输出"摘要："等标签"""

    return llm.invoke(system_prompt, user_prompt)


def _summarize_cluster_fallback(label: str, items: List[Dict[str, str]]) -> str:
    first = items[0] if items else {}
    content = (first.get("content") or "").strip()
    if not content:
        titles = [i.get("title", "") for i in items[:4] if i.get("title")]
        return "；".join(titles) if titles else "暂无可用摘要。"
    return content[:260] + ("..." if len(content) > 260 else "")


def _cluster_sort_key(items: List[Dict[str, str]]) -> str:
    latest = ""
    for item in items:
        ts = item.get("published_at") or item.get("created_at") or ""
        if ts and ts > latest:
            latest = ts
    return latest


def generate_brief_markdown(topic_name: str, clusters: Dict[str, List[Dict[str, str]]]) -> str:
    llm = _get_llm()
    date_str = datetime.now().strftime("%Y-%m-%d")

    total_items = sum(len(v) for v in clusters.values())
    source_counts: Dict[str, int] = {}
    for items in clusters.values():
        for item in items:
            source = item.get("source", "") or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

    source_line = " · ".join([f"{k}: {v}" for k, v in source_counts.items()]) if source_counts else "暂无来源统计"

    lines = [
        f"# {date_str} {topic_name} 每日简讯",
        "",
        f"> 共 {total_items} 篇内容。",
        f"> 来源统计：{source_line}",
        "",
        "## TLDR",
        "",
    ]

    tldr_topics = list(clusters.keys())[:5]
    lines.append("、".join(tldr_topics) if tldr_topics else "暂无主题")
    lines.append("")
    lines.append("---")
    lines.append("")

    sorted_clusters = sorted(clusters.items(), key=lambda kv: _cluster_sort_key(kv[1]), reverse=True)

    for idx, (label, items) in enumerate(sorted_clusters, start=1):
        # Sort items inside cluster by time (newest first)
        items_sorted = sorted(
            items,
            key=lambda x: x.get("published_at") or x.get("created_at") or "",
            reverse=True,
        )

        lines.append(f"## {idx}. {label}")
        lines.append("")
        if llm:
            try:
                summary = _summarize_cluster_with_llm(llm, label, items_sorted)
            except Exception:
                summary = _summarize_cluster_fallback(label, items_sorted)
        else:
            summary = _summarize_cluster_fallback(label, items_sorted)
        lines.append(summary)
        lines.append("")

        # Append top headlines for quick scan
        headlines = [i.get("title", "") for i in items_sorted[:3] if i.get("title")]
        if headlines:
            lines.append("**重点标题：**")
            for h in headlines:
                lines.append(f"- {h}")
            lines.append("")

        lines.append(f"*(相关文章 {len(items_sorted)} 篇)*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def build_brief_for_topic(topic, items: List[Dict[str, str]]) -> str:
    clusters = cluster_by_keywords(items, topic.keywords)
    return generate_brief_markdown(topic.name, clusters)
