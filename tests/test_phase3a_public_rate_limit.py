"""Tests for public GET rate limits in api_key_guard middleware."""

import asyncio
import json
import os
import sys

from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from backend.rate_limit import InMemoryRateLimiter


def _make_request(path: str, client_ip: str = "198.51.100.20") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _pass_through(_request: Request) -> Response:
    return Response(status_code=200)


def _call_guard(path: str, ip: str = "198.51.100.20") -> Response:
    req = _make_request(path, ip)
    return asyncio.run(m.api_key_guard(req, _pass_through))


def test_public_read_limit_hits_429(monkeypatch):
    monkeypatch.setattr(m, "DISABLE_AUTH", False)
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "")
    monkeypatch.setattr(m, "_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(m, "PUBLIC_READ_RATE_LIMIT", 2)
    monkeypatch.setattr(m, "PUBLIC_EXPORT_RATE_LIMIT", 10)

    r1 = _call_guard("/api/health")
    r2 = _call_guard("/api/health")
    r3 = _call_guard("/api/health")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    payload = json.loads(r3.body.decode("utf-8"))
    assert payload["error_code"] == "RATE_LIMITED_PUBLIC"


def test_export_limit_is_independent_from_public_read(monkeypatch):
    monkeypatch.setattr(m, "DISABLE_AUTH", False)
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "")
    monkeypatch.setattr(m, "_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(m, "PUBLIC_READ_RATE_LIMIT", 10)
    monkeypatch.setattr(m, "PUBLIC_EXPORT_RATE_LIMIT", 1)

    export_ok = _call_guard("/api/briefs/1/export")
    export_blocked = _call_guard("/api/briefs/1/export")
    read_ok = _call_guard("/api/topics")

    assert export_ok.status_code == 200
    assert export_blocked.status_code == 429
    assert read_ok.status_code == 200
