"""Content collection utilities (RSS + Tavily)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import html
import os
import re
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser

try:
    from tavily import TavilyClient
except Exception:  # pragma: no cover
    TavilyClient = None


@dataclass
class CollectedItem:
    title: str
    url: str
    content: str
    source: str
    source_type: str = "rss"
    published_at: Optional[str] = None


class Collector:
    def __init__(self, tavily_api_key: str | None = None) -> None:
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY", "")
        self.tavily_enabled = bool(self.tavily_api_key and TavilyClient is not None)
        self.tavily_client = None
        if self.tavily_enabled:
            try:
                self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
            except Exception:
                # Fail closed: disable Tavily instead of breaking collection.
                self.tavily_client = None
                self.tavily_enabled = False

    def fetch_rss(self, url: str) -> List[CollectedItem]:
        feed = feedparser.parse(url)
        source = (feed.feed.get("title") if hasattr(feed, "feed") else None) or _extract_domain(url)
        items: List[CollectedItem] = []
        feed_domain = _extract_domain(url)
        for entry in feed.entries:
            published_at = self._parse_date(entry)
            raw_entry_content = self._extract_entry_content(entry)
            content = raw_entry_content
            link = entry.get("link", "")
            # HN RSS often provides only metadata in summary and article URL separately.
            if "hnrss.org" in feed_domain or "news.ycombinator.com" in feed_domain:
                article_url = _extract_hn_article_url(raw_entry_content)
                if article_url:
                    link = article_url
            cleaned = self._clean_text(content)
            title_clean = self._clean_text(entry.get("title", ""))
            if _looks_like_feed_metadata_noise(cleaned):
                if title_clean:
                    # Keep body empty when feed only exposes metadata fields.
                    # Downstream UI can show "No excerpt available" without noise text.
                    cleaned = ""
            elif _looks_like_title_echo(cleaned, title_clean):
                # If feed body is basically a title echo, keep excerpt empty.
                cleaned = ""
            items.append(
                CollectedItem(
                    title=entry.get("title", ""),
                    url=link,
                    content=cleaned,
                    source=source,
                    source_type="rss",
                    published_at=published_at,
                )
            )
        return items

    def _extract_entry_content(self, entry) -> str:
        """Best-effort content extraction from common RSS/Atom fields."""
        # 1) content:encoded / content list (often full body)
        content_field = entry.get("content")
        if isinstance(content_field, list):
            for part in content_field:
                if not isinstance(part, dict):
                    continue
                value = part.get("value") or part.get("content") or ""
                if isinstance(value, str) and value.strip():
                    return value
        elif isinstance(content_field, dict):
            value = content_field.get("value") or content_field.get("content") or ""
            if isinstance(value, str) and value.strip():
                return value
        elif isinstance(content_field, str) and content_field.strip():
            return content_field

        # 2) summary/detail fields
        summary_detail = entry.get("summary_detail")
        if isinstance(summary_detail, dict):
            value = summary_detail.get("value") or ""
            if isinstance(value, str) and value.strip():
                return value

        # 3) legacy description/summary
        return entry.get("summary", "") or entry.get("description", "") or ""

    def fetch_tavily(self, query: str, max_results: int = 5) -> List[CollectedItem]:
        if not self.tavily_enabled or not self.tavily_client:
            return []
        resp = self.tavily_client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False,
            include_images=False,
        )
        results = []
        # Use current time as fallback for Tavily results
        now = datetime.utcnow().isoformat()

        for item in resp.get("results", []):
            results.append(
                CollectedItem(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    source="tavily",
                    source_type="tavily",
                    published_at=now,
                )
            )
        return results

    def enrich_item_with_tavily(self, item: CollectedItem) -> CollectedItem:
        """Best-effort enrichment for low-signal RSS entries using Tavily."""
        if not self.tavily_enabled or not self.tavily_client:
            return item
        query = item.url or item.title
        if not query:
            return item
        try:
            resp = self.tavily_client.search(
                query=query,
                max_results=2,
                search_depth="advanced",
                include_answer=False,
                include_images=False,
            )
            results = resp.get("results", []) or []
            if not results:
                return item
            chosen = None
            item_url = (item.url or "").strip().lower()
            for row in results:
                row_url = str(row.get("url") or "").strip().lower()
                if item_url and row_url == item_url:
                    chosen = row
                    break
            if chosen is None:
                chosen = results[0]
            candidate = self._clean_text(chosen.get("content", "") or "")
            if not candidate:
                return item
            # Replace only when better than existing content.
            if len(candidate.strip()) > len((item.content or "").strip()):
                item.content = candidate
            chosen_url = str(chosen.get("url") or "").strip()
            if chosen_url:
                item.url = chosen_url
            return item
        except Exception:
            return item

    def _is_recent(self, published_at: Optional[str], max_age_hours: int, allow_undated: bool) -> bool:
        if not published_at:
            return allow_undated
        try:
            ts = published_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo:
                dt = dt.astimezone(tz=None).replace(tzinfo=None)
        except Exception:
            return allow_undated
        return dt >= (datetime.utcnow() - timedelta(hours=max_age_hours))

    def _parse_date(self, entry) -> Optional[str]:
        parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if parsed:
            try:
                return datetime(*parsed[:6]).isoformat()
            except Exception:
                return None
        raw = entry.get("published") or entry.get("updated")
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo:
                dt = dt.astimezone(tz=None).replace(tzinfo=None)
            return dt.isoformat()
        except Exception:
            return None

    def _clean_text(self, text: str) -> str:
        """Clean HTML tags, entities, and URLs from text."""
        if not text:
            return ""

        # 1. Decode HTML entities (&nbsp; -> space, &quot; -> ")
        text = html.unescape(text)

        # 2. Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # 3. Remove URLs
        text = re.sub(r'https?://\S+', '', text)

        # 4. Normalize whitespace
        text = ' '.join(text.split())

        return text


_NOISE_PATTERNS = [
    r"article\s+url\s*:",
    r"comments?\s+url\s*:",
    r"points?\s*:\s*\d+",
    r"#\s*comments?\s*:\s*\d+",
    r"\[\s*publishedat\s*\]",
]


def _looks_like_feed_metadata_noise(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    hits = sum(1 for p in _NOISE_PATTERNS if re.search(p, lowered))
    if hits >= 2:
        return True
    if len(lowered) < 35:
        return True
    words = lowered.split()
    if words and sum(1 for w in words if "url" in w or "comment" in w) >= 2:
        return True
    return False


def _extract_hn_article_url(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    m = re.search(r"article\s+url\s*:\s*(https?://\S+)", raw, flags=re.IGNORECASE)
    if not m:
        return ""
    url = m.group(1).strip().rstrip(".,)")
    return url


def _normalize_compare_text(text: str) -> str:
    lowered = (text or "").lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _looks_like_title_echo(content: str, title: str) -> bool:
    c = _normalize_compare_text(content)
    t = _normalize_compare_text(title)
    if not c or not t:
        return False
    if c == t:
        return True
    if c.startswith(t):
        tail = c[len(t):].strip()
        # title + very short filler = still title echo
        if len(tail) < 24:
            return True
    # repeated headline pattern
    if c.count(t) >= 2:
        remainder = c.replace(t, " ").strip()
        if len(remainder) < 36:
            return True
    return False


def _extract_domain(url: str) -> str:
    """Return a clean domain name from a URL (e.g. 'reuters.com')."""
    try:
        host = urlparse(url).hostname or ""
        return re.sub(r'^www\.', '', host)
    except Exception:
        return url


def _is_homepage_url(url: str) -> bool:
    """Return True if the URL points to a site root (no meaningful path)."""
    try:
        parsed = urlparse(url)
        return parsed.path.strip("/") == "" and not parsed.query
    except Exception:
        return False


def _path_depth(url: str) -> int:
    try:
        parsed = urlparse(url)
        return len([segment for segment in parsed.path.split("/") if segment.strip()])
    except Exception:
        return 0


def _is_blacklisted_path(url: str) -> bool:
    """Filter obvious non-article paths such as /, /index, /tag, /category, /search."""
    try:
        path = (urlparse(url).path or "").strip("/").lower()
    except Exception:
        return True
    if path == "":
        return True
    first = path.split("/")[0]
    blocked = {
        "index",
        "index.html",
        "tag",
        "tags",
        "category",
        "categories",
        "search",
    }
    return first in blocked


def _passes_quality_gate(
    item: CollectedItem,
    min_title_len: int,
    min_content_len: int,
    min_path_depth: int,
) -> bool:
    title = (item.title or "").strip()
    content = (item.content or "").strip()
    if len(title) < min_title_len:
        return False
    if len(content) < min_content_len:
        return False
    if _is_homepage_url(item.url):
        return False
    if _is_blacklisted_path(item.url):
        return False
    if _path_depth(item.url) < min_path_depth:
        return False
    return True


def _dedupe_by_url(items: List[CollectedItem]) -> List[CollectedItem]:
    seen = set()
    deduped: List[CollectedItem] = []
    for item in items:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)
    return deduped


_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "not", "no", "it", "its",
    "that", "this", "these", "those", "than", "then", "so", "if", "as",
})


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation & stop words for fuzzy dedup."""
    lowered = title.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", lowered)
    tokens = [t for t in cleaned.split() if t and t not in _STOP_WORDS]
    return " ".join(tokens)


def _build_keyword_terms(keywords: List[str]) -> List[str]:
    terms: List[str] = []
    for kw in keywords or []:
        raw = (kw or "").strip().lower()
        if not raw:
            continue
        # Support lightweight boolean expression style:
        # "openai | anthropic" -> ["openai", "anthropic"]
        for token in re.split(r"[|,/;]+", raw):
            token = token.strip()
            if len(token) >= 2:
                terms.append(token)
    # Keep insertion order while deduping
    seen = set()
    ordered: List[str] = []
    for item in terms:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _keyword_match_score(item: CollectedItem, terms: List[str]) -> int:
    title = (item.title or "").lower()
    content = (item.content or "").lower()
    score = 0
    for term in terms:
        title_hits = title.count(term)
        content_hits = content.count(term)
        score += title_hits * 3 + content_hits
    return score


def _apply_keyword_matrix(
    items: List[CollectedItem],
    keywords: List[str],
    min_score: int,
    arxiv_min_score: int,
    arxiv_max_items: int,
) -> List[CollectedItem]:
    terms = _build_keyword_terms(keywords)
    if not terms:
        return items

    scored: List[tuple[CollectedItem, int]] = []
    for item in items:
        score = _keyword_match_score(item, terms)
        domain = _extract_domain(item.url or "")
        required = arxiv_min_score if domain.endswith("arxiv.org") else min_score
        if score >= required:
            scored.append((item, score))

    if not scored:
        return []

    non_arxiv: List[tuple[CollectedItem, int]] = []
    arxiv_items: List[tuple[CollectedItem, int]] = []
    for pair in scored:
        domain = _extract_domain(pair[0].url or "")
        if domain.endswith("arxiv.org"):
            arxiv_items.append(pair)
        else:
            non_arxiv.append(pair)

    arxiv_items.sort(key=lambda x: x[1], reverse=True)
    capped_arxiv = arxiv_items[: max(0, arxiv_max_items)]
    merged = non_arxiv + capped_arxiv
    return [item for item, _ in merged]


def _dedupe_by_title(items: List[CollectedItem]) -> List[CollectedItem]:
    """Remove items with near-identical titles (same article, different URLs)."""
    seen: set = set()
    deduped: List[CollectedItem] = []
    for item in items:
        norm = _normalize_title(item.title)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(item)
    return deduped


def collect_for_topic(topic, collector: Collector, max_tavily_results: int = 5) -> Dict[str, Any]:
    max_age_hours = int(os.getenv("ARCBRIEF_NEWS_MAX_AGE_HOURS", "48"))
    allow_undated = os.getenv("ARCBRIEF_ALLOW_UNDATED", "1") == "1"
    rss_require_published = os.getenv("ARCBRIEF_RSS_REQUIRE_PUBLISHED", "1") == "1"
    rss_only = os.getenv("ARCBRIEF_RSS_ONLY", "0") == "1"
    tavily_enabled = collector.tavily_enabled and not rss_only
    min_rss_before_tavily = int(os.getenv("ARCBRIEF_MIN_RSS_ITEMS_BEFORE_TAVILY", "12"))
    min_title_len = int(os.getenv("ARCBRIEF_MIN_TITLE_LEN", "12"))
    min_content_len = int(os.getenv("ARCBRIEF_MIN_CONTENT_LEN", "40"))
    min_path_depth = int(os.getenv("ARCBRIEF_MIN_URL_PATH_DEPTH", "1"))
    enable_keyword_matrix = os.getenv("ARCBRIEF_ENABLE_KEYWORD_MATRIX", "1") == "1"
    keyword_min_score = int(os.getenv("ARCBRIEF_KEYWORD_MIN_SCORE", "1"))
    arxiv_min_score = int(os.getenv("ARCBRIEF_ARXIV_MIN_SCORE", "2"))
    arxiv_max_items = int(os.getenv("ARCBRIEF_ARXIV_MAX_ITEMS", "3"))
    enable_tavily_enrich = os.getenv("ARCBRIEF_TAVILY_ENRICH_EMPTY", "1") == "1"
    tavily_enrich_max_items = int(os.getenv("ARCBRIEF_TAVILY_ENRICH_MAX_ITEMS", "12"))

    rss_items: List[CollectedItem] = []
    rss_health_stats: List[Dict[str, Any]] = []
    for rss_url in topic.rss_sources:
        try:
            fetched = collector.fetch_rss(rss_url)
            rss_items.extend(fetched)
            rss_health_stats.append({
                "rss_url": rss_url,
                "status": "ok" if fetched else "empty",
                "items_fetched": len(fetched),
                "last_error": None,
            })
        except Exception as exc:
            rss_health_stats.append({
                "rss_url": rss_url,
                "status": "error",
                "items_fetched": 0,
                "last_error": str(exc)[:200],
            })

    # RSS first: prefer source-native publish times for freshness reliability.
    if rss_require_published:
        rss_items = [item for item in rss_items if item.published_at]
    rss_items = [
        item for item in rss_items
        if collector._is_recent(item.published_at, max_age_hours, allow_undated)
    ]
    rss_items = _dedupe_by_url(rss_items)
    rss_items = _dedupe_by_title(rss_items)
    if enable_tavily_enrich and tavily_enabled:
        enriched = 0
        for item in rss_items:
            if enriched >= max(0, tavily_enrich_max_items):
                break
            low_signal = (
                not (item.content or "").strip()
                or _looks_like_title_echo(item.content, item.title)
                or len((item.content or "").strip()) < min_content_len
            )
            if not low_signal:
                continue
            before_len = len((item.content or "").strip())
            collector.enrich_item_with_tavily(item)
            after_len = len((item.content or "").strip())
            if after_len > before_len:
                enriched += 1
    rss_items = [
        item for item in rss_items
        if _passes_quality_gate(item, min_title_len, min_content_len, min_path_depth)
    ]
    if enable_keyword_matrix and topic.keywords:
        rss_items = _apply_keyword_matrix(
            rss_items,
            topic.keywords,
            min_score=keyword_min_score,
            arxiv_min_score=arxiv_min_score,
            arxiv_max_items=arxiv_max_items,
        )

    items: List[CollectedItem] = list(rss_items)

    # Tavily is supplement only, triggered when RSS volume is insufficient.
    if tavily_enabled and len(rss_items) < min_rss_before_tavily:
        supplement: List[CollectedItem] = []
        for kw in topic.keywords:
            supplement.extend(collector.fetch_tavily(kw, max_results=max_tavily_results))
        supplement = [
            item for item in supplement
            if collector._is_recent(item.published_at, max_age_hours, allow_undated)
        ]
        supplement = _dedupe_by_url(supplement)
        supplement = _dedupe_by_title(supplement)
        rss_urls = {r.url for r in rss_items}
        rss_titles = {_normalize_title(r.title) for r in rss_items}
        supplement = [
            item for item in supplement
            if item.url not in rss_urls
            and _normalize_title(item.title) not in rss_titles
            and _passes_quality_gate(item, min_title_len, min_content_len, min_path_depth)
        ]
        if enable_keyword_matrix and topic.keywords:
            supplement = _apply_keyword_matrix(
                supplement,
                topic.keywords,
                min_score=keyword_min_score,
                arxiv_min_score=arxiv_min_score,
                arxiv_max_items=arxiv_max_items,
            )
        items.extend(supplement)

    return {
        "items": [
            {
                "title": item.title,
                "url": item.url,
                "content": item.content,
                "source": item.source,
                "source_type": item.source_type,
                "published_at": item.published_at,
            }
            for item in items
        ],
        "rss_health": rss_health_stats,
    }
