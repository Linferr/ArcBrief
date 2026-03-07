"""Tests for Phase 4A /api/tldr ingestion and cache pipeline."""

import os
import sys

import pytest
from fastapi import HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db import ArcBriefDB
import backend.main as main
from backend.scraper import ScrapedDocument


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db = ArcBriefDB(str(tmp_path / "tldr.db"))
    monkeypatch.setattr(main, "DB", db)
    return db


def test_create_tldr_ingests_and_caches_document(temp_db, monkeypatch):
    calls = {"fetch": 0}

    def fake_fetch(url: str) -> ScrapedDocument:
        calls["fetch"] += 1
        return ScrapedDocument(
            url=url,
            final_url=url,
            title="Example Article",
            content="This is a long article body about agent workflows and structured intelligence summaries." * 4,
            source_domain="example.com",
        )

    monkeypatch.setattr(main, "fetch_tldr_document", fake_fetch)
    monkeypatch.setattr(main, "llm_chat", lambda system, user: "Compact summary for mobile reading.")

    req = main.TLDRRequest(url="https://example.com/article", language="English (US)", created_by="discord:42")
    first = main.create_tldr(req)
    second = main.create_tldr(req)

    assert first["cached"] is False
    assert first["ingested"] is True
    assert first["title"] == "Example Article"
    assert first["summary"] == "Compact summary for mobile reading."
    assert first["source_domain"] == "example.com"

    assert second["cached"] is True
    assert second["summary"] == "Compact summary for mobile reading."
    assert calls["fetch"] == 1

    row = temp_db.get_user_ingestion("https://example.com/article")
    assert row is not None
    assert row["title"] == "Example Article"
    assert row["created_by"] == "discord:42"


def test_create_tldr_rejects_localhost_and_private_targets(temp_db):
    with pytest.raises(HTTPException) as exc:
        main.create_tldr(main.TLDRRequest(url="http://127.0.0.1:8000/private"))

    assert exc.value.status_code == 400
    assert "public http/https URL" in str(exc.value.detail)
