"""Tests for Discord bot command-resolution helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot_helpers import (
    build_topic_autocomplete_matches,
    is_discord_admin,
    parse_admin_ids,
    resolve_topic_reference,
)


TOPICS = [
    {"id": 1, "name": "Global Trending"},
    {"id": 3, "name": "AI Daily"},
    {"id": 4, "name": "AI Policy & Safety"},
]


def test_resolve_topic_reference_accepts_numeric_topic_id():
    topic, error = resolve_topic_reference("3", TOPICS)
    assert error is None
    assert topic is not None
    assert topic["id"] == 3


def test_resolve_topic_reference_accepts_topic_name():
    topic, error = resolve_topic_reference("ai daily", TOPICS)
    assert error is None
    assert topic is not None
    assert topic["name"] == "AI Daily"


def test_resolve_topic_reference_reports_missing_topic():
    topic, error = resolve_topic_reference("unknown topic", TOPICS)
    assert topic is None
    assert "Topic not found" in (error or "")


def test_resolve_topic_reference_reports_multiple_matches():
    topic, error = resolve_topic_reference("ai", TOPICS)
    assert topic is None
    assert "Multiple topics matched" in (error or "")
    assert "3 | AI Daily" in (error or "")
    assert "4 | AI Policy & Safety" in (error or "")


def test_parse_admin_ids_ignores_invalid_tokens():
    parsed = parse_admin_ids("123, abc, 456 , ,789")
    assert parsed == {123, 456, 789}


def test_is_discord_admin_checks_membership():
    assert is_discord_admin(42, "1,42,99")
    assert not is_discord_admin(7, "1,42,99")


def test_build_topic_autocomplete_matches_prefers_name_matches():
    matches = build_topic_autocomplete_matches("ai", TOPICS)
    assert matches[0] == ("3 | AI Daily", "AI Daily")
    assert matches[1] == ("4 | AI Policy & Safety", "AI Policy & Safety")


def test_build_topic_autocomplete_matches_supports_numeric_lookup():
    matches = build_topic_autocomplete_matches("3", TOPICS)
    assert matches[0] == ("3 | AI Daily", "AI Daily")
