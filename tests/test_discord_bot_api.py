"""Tests for Discord bot API error surface."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from discord_bot_api import build_api_error_message


def test_build_api_error_message_prefers_structured_message():
    msg = build_api_error_message(
        "POST",
        "/tldr",
        502,
        '{"error_code":"HTTP_502","message":"Failed to fetch URL: 404 Client Error"}',
    )

    assert msg == "POST /tldr failed: 502: Failed to fetch URL: 404 Client Error"


def test_build_api_error_message_falls_back_to_raw_body():
    msg = build_api_error_message("DELETE", "/bookmarks", 404, "Bookmark not found")

    assert msg == "DELETE /bookmarks failed: 404: Bookmark not found"
