"""Tests for P1-1: RSS health tracking via collect_for_topic."""
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.collection import CollectedItem, collect_for_topic


class HealthTrackingCollector:
    """Collector stub that returns items for the first feed and fails on the second."""
    tavily_enabled = False

    def fetch_rss(self, url: str):
        if "good" in url:
            return [
                CollectedItem(
                    title="Good article from reliable source",
                    url=f"https://example.com/news/{url.split('/')[-1]}",
                    content="Detailed content about important events " + ("x" * 80),
                    source="GoodSource",
                    source_type="rss",
                    published_at="2026-02-10T08:00:00",
                )
            ]
        raise ConnectionError("DNS resolution failed")

    def fetch_tavily(self, _query, max_results=5):
        return []

    def _is_recent(self, published_at, max_age_hours, allow_undated):
        return True


def test_rss_health_tracks_ok_and_error(monkeypatch):
    monkeypatch.setenv("ARCBRIEF_RSS_ONLY", "1")
    topic = SimpleNamespace(
        rss_sources=["https://feeds.good/rss.xml", "https://feeds.broken/rss.xml"],
        keywords=["test"],
    )
    result = collect_for_topic(topic, HealthTrackingCollector())

    health = result["rss_health"]
    assert len(health) == 2

    good = next(h for h in health if "good" in h["rss_url"])
    assert good["status"] == "ok"
    assert good["items_fetched"] == 1
    assert good["last_error"] is None

    broken = next(h for h in health if "broken" in h["rss_url"])
    assert broken["status"] == "error"
    assert broken["items_fetched"] == 0
    assert "DNS resolution failed" in broken["last_error"]


def test_rss_health_marks_empty_feeds(monkeypatch):
    monkeypatch.setenv("ARCBRIEF_RSS_ONLY", "1")

    class EmptyCollector:
        tavily_enabled = False
        def fetch_rss(self, _url):
            return []
        def fetch_tavily(self, _q, max_results=5):
            return []
        def _is_recent(self, pa, mah, au):
            return True

    topic = SimpleNamespace(rss_sources=["https://feeds.empty/rss.xml"], keywords=[])
    result = collect_for_topic(topic, EmptyCollector())

    health = result["rss_health"]
    assert len(health) == 1
    assert health[0]["status"] == "empty"
    assert health[0]["items_fetched"] == 0
