"""Tests for Phase 4A layered /api/chat context selection."""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main
from foreign_query_agent.tools.base import SearchResponse, SearchResult


def _setup_db(tmp_path):
    db = ArcBriefDB(str(tmp_path / "chat_layers.db"))
    db.create_topic(
        {
            "name": "AI Daily",
            "keywords": ["ai"],
            "rss_sources": [],
            "scrape_frequency_hours": 4,
            "push_time": "08:00",
            "push_channels": ["discord"],
        }
    )
    return db


def test_chat_prefers_brief_context(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    db.save_brief(1, "2026-03-06", "OpenAI shipping updates and agent orchestration changes.", 3)
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "answer from briefs")

    result = main.chat_with_briefs(main.ChatRequest(message="OpenAI news?", topic_id=1))

    assert result["reply"] == "answer from briefs"
    assert result["context_layer"] == "brief_context"
    assert result["sources"]


def test_chat_falls_back_to_article_context_when_briefs_missing(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    db.save_articles(
        1,
        [
            {
                "title": "Agent workflow launch",
                "url": "https://example.com/agent",
                "content": "A new agent workflow launch explains how orchestration improved developer velocity.",
                "source": "example.com",
                "published_at": "2026-03-06T10:00:00",
            }
        ],
    )
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "answer from articles")

    result = main.chat_with_briefs(main.ChatRequest(message="agent workflow launch", topic_id=1, days=30))

    assert result["reply"] == "answer from articles"
    assert result["context_layer"] == "article_context"
    assert result["sources"][0].startswith("Article |")


def test_chat_falls_back_to_ingestion_context(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    db.save_user_ingestion(
        url="https://example.com/mcp",
        final_url="https://example.com/mcp",
        title="MCP ecosystem note",
        content="This note explains MCP adoption and vendor support.",
        summary="MCP adoption is expanding.",
        source_domain="example.com",
        language_used="English (US)",
        created_by="discord:42",
    )
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "answer from ingestions")

    result = main.chat_with_briefs(main.ChatRequest(message="MCP adoption"))

    assert result["reply"] == "answer from ingestions"
    assert result["context_layer"] == "ingestion_context"
    assert result["sources"][0].startswith("Ingestion |")


def test_chat_uses_web_fallback_when_local_context_missing(tmp_path, monkeypatch):
    db = _setup_db(tmp_path)
    monkeypatch.setattr(main, "DB", db)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "answer from live web")

    class DummyTool:
        def search(self, query: str, max_results: int = 5):
            return SearchResponse(
                query=query,
                results=[
                    SearchResult(
                        title="Live web result",
                        url="https://live.example.com/post",
                        content="Fresh web content about the latest model release.",
                    )
                ],
            )

    monkeypatch.setattr(
        main,
        "create_search_tool_with_meta",
        lambda *args, **kwargs: (
            DummyTool(),
            SimpleNamespace(provider_effective="Tavily Search API", fallback_reason="", llm_assisted_search=False),
        ),
    )

    result = main.chat_with_briefs(main.ChatRequest(message="latest model release"))

    assert result["reply"] == "answer from live web"
    assert result["context_layer"] == "web_fallback"
    assert result["sources"][0].startswith("Web |")
