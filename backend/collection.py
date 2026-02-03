"""Content collection utilities (RSS + Tavily)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import html
import os
import re

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
    published_at: Optional[str] = None


class Collector:
    def __init__(self, tavily_api_key: str | None = None) -> None:
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY", "")
        self.tavily_client = None
        if self.tavily_api_key and TavilyClient is not None:
            self.tavily_client = TavilyClient(api_key=self.tavily_api_key)

    def fetch_rss(self, url: str) -> List[CollectedItem]:
        feed = feedparser.parse(url)
        source = (feed.feed.get("title") if hasattr(feed, "feed") else None) or url
        items: List[CollectedItem] = []
        for entry in feed.entries:
            published_at = self._parse_date(entry)
            content = entry.get("summary", "") or entry.get("description", "") or ""
            items.append(
                CollectedItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    content=self._clean_text(content),
                    source=source,
                    published_at=published_at,
                )
            )
        return items

    def fetch_tavily(self, query: str, max_results: int = 5) -> List[CollectedItem]:
        if not self.tavily_client:
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
                    published_at=now,
                )
            )
        return results

    def _parse_date(self, entry) -> Optional[str]:
        parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if not parsed:
            return None
        try:
            return datetime(*parsed[:6]).isoformat()
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


def collect_for_topic(topic, collector: Collector, max_tavily_results: int = 5) -> List[Dict[str, str]]:
    items: List[CollectedItem] = []

    for rss_url in topic.rss_sources:
        items.extend(collector.fetch_rss(rss_url))

    for kw in topic.keywords:
        items.extend(collector.fetch_tavily(kw, max_results=max_tavily_results))

    seen = set()
    deduped: List[CollectedItem] = []
    for item in items:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)

    return [
        {
            "title": item.title,
            "url": item.url,
            "content": item.content,
            "source": item.source,
            "published_at": item.published_at,
        }
        for item in deduped
    ]
