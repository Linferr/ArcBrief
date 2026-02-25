import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.collection import (
    _apply_keyword_matrix,
    CollectedItem,
    Collector,
    _looks_like_feed_metadata_noise,
    _passes_quality_gate,
    collect_for_topic,
)


def test_quality_gate_rejects_home_and_low_content():
    bad_home = CollectedItem(
        title="Breaking update",
        url="https://example.com/",
        content="x" * 120,
        source="example",
        source_type="rss",
        published_at="2026-02-09T10:00:00",
    )
    assert not _passes_quality_gate(bad_home, 12, 40, 1)

    bad_short = CollectedItem(
        title="short",
        url="https://example.com/news/abc",
        content="too short",
        source="example",
        source_type="rss",
        published_at="2026-02-09T10:00:00",
    )
    assert not _passes_quality_gate(bad_short, 12, 40, 1)


def test_collect_for_topic_rss_only_skips_tavily(monkeypatch):
    class DummyCollector:
        tavily_enabled = True

        def __init__(self):
            self.tavily_calls = 0

        def fetch_rss(self, _url):
            return [
                CollectedItem(
                    title="Reuters market volatility update",
                    url="https://reuters.com/world/us/market-volatility-123",
                    content="Detailed market story " + ("x" * 100),
                    source="Reuters",
                    source_type="rss",
                    published_at="2026-02-09T09:00:00",
                )
            ]

        def fetch_tavily(self, _query, max_results=5):
            self.tavily_calls += 1
            return []

        def _is_recent(self, published_at, max_age_hours, allow_undated):
            return True

    monkeypatch.setenv("ARCBRIEF_RSS_ONLY", "1")
    topic = SimpleNamespace(
        rss_sources=["https://fake/rss.xml"],
        keywords=["market"],
    )
    collector = DummyCollector()
    result = collect_for_topic(topic, collector)
    items = result["items"]

    assert len(items) == 1
    assert items[0]["source_type"] == "rss"
    assert collector.tavily_calls == 0
    assert "rss_health" in result
    assert len(result["rss_health"]) == 1


def test_collector_disables_tavily_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    collector = Collector()
    assert collector.tavily_enabled is False
    assert collector.fetch_tavily("ai") == []


def test_hn_metadata_noise_detection():
    noisy = "Article URL: Comments URL: Points: 12 # Comments: 2 [publishedat]"
    clean = "OpenAI released a new policy update for enterprise safety controls."
    assert _looks_like_feed_metadata_noise(noisy) is True
    assert _looks_like_feed_metadata_noise(clean) is False


def test_keyword_matrix_filters_unrelated_content():
    items = [
        CollectedItem(
            title="OpenAI launches new safety report",
            url="https://openai.com/blog/safety-2026",
            content="OpenAI and GPT roadmap with policy details.",
            source="OpenAI Blog",
            source_type="rss",
            published_at="2026-02-12T08:00:00",
        ),
        CollectedItem(
            title="General business update",
            url="https://example.com/business/update-1",
            content="Company revenue and retail outlook.",
            source="Example News",
            source_type="rss",
            published_at="2026-02-12T07:00:00",
        ),
    ]
    filtered = _apply_keyword_matrix(
        items,
        keywords=["OpenAI", "GPT", "Anthropic"],
        min_score=1,
        arxiv_min_score=2,
        arxiv_max_items=3,
    )
    assert len(filtered) == 1
    assert "openai" in filtered[0].title.lower()


def test_keyword_matrix_caps_arxiv_items():
    items = [
        CollectedItem(
            title=f"Agentic RAG paper {idx}",
            url=f"https://arxiv.org/abs/2501.00{idx}",
            content="Agentic RAG architecture with transformer benchmarks.",
            source="arXiv",
            source_type="rss",
            published_at="2026-02-12T08:00:00",
        )
        for idx in range(5)
    ]
    filtered = _apply_keyword_matrix(
        items,
        keywords=["Agentic", "RAG", "Transformer"],
        min_score=1,
        arxiv_min_score=2,
        arxiv_max_items=3,
    )
    assert len(filtered) == 3
