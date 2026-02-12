"""Tests for P1-3: title normalization dedup."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.collection import (
    CollectedItem,
    _normalize_title,
    _dedupe_by_title,
)


def _item(title: str, url: str = "https://example.com/article") -> CollectedItem:
    return CollectedItem(
        title=title,
        url=url,
        content="Some article content that is long enough.",
        source="test",
        source_type="rss",
        published_at="2026-02-10T10:00:00",
    )


def test_normalize_title_strips_punctuation_and_stop_words():
    assert _normalize_title("The Big AI Revolution: Is It Real?") == "big ai revolution real"
    assert _normalize_title("  GOLD PRICE surges! ") == "gold price surges"
    assert _normalize_title("") == ""


def test_dedupe_by_title_removes_same_article_different_urls():
    items = [
        _item("Gold Price Surges to Record High", "https://reuters.com/gold-1"),
        _item("Gold Price Surges to Record High!", "https://cnbc.com/gold-2"),
        _item("Silver Price Drops Sharply", "https://reuters.com/silver-1"),
    ]
    deduped = _dedupe_by_title(items)
    assert len(deduped) == 2
    assert deduped[0].url == "https://reuters.com/gold-1"
    assert deduped[1].url == "https://reuters.com/silver-1"


def test_dedupe_by_title_keeps_different_articles():
    items = [
        _item("Fed Raises Interest Rate by 25 Basis Points"),
        _item("Treasury Yield Hits 5% for First Time Since 2007"),
        _item("CPI Data Shows Inflation Cooling"),
    ]
    deduped = _dedupe_by_title(items)
    assert len(deduped) == 3
