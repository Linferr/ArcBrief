"""Tests for the public read-only demo guardrails."""

import asyncio
import json
import os
import sys

from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m
from backend.rate_limit import InMemoryRateLimiter


def _make_request(
    path: str,
    method: str = "GET",
    api_key: str = "",
    client_ip: str = "198.51.100.30",
) -> Request:
    headers = []
    if api_key:
        headers.append((b"x-api-key", api_key.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _pass_through(_request: Request) -> Response:
    return Response(status_code=200)


def _call_guard(request: Request) -> Response:
    return asyncio.run(m.api_key_guard(request, _pass_through))


def _enable_demo(monkeypatch, enabled: bool = True) -> None:
    monkeypatch.setattr(m, "PUBLIC_DEMO_READ_ONLY", enabled)
    monkeypatch.setattr(m, "DISABLE_AUTH", False)
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "")
    monkeypatch.setattr(m, "_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(m, "PUBLIC_READ_RATE_LIMIT", 1000)
    monkeypatch.setattr(m, "PUBLIC_EXPORT_RATE_LIMIT", 1000)
    monkeypatch.setenv("ARCBRIEF_PUBLIC_API_KEY", "guest-key")
    monkeypatch.setenv("ARCBRIEF_API_KEY", "admin-key")


def test_guest_run_is_blocked_in_read_only_demo(monkeypatch):
    _enable_demo(monkeypatch)

    response = _call_guard(_make_request("/api/run", method="POST", api_key="guest-key"))

    assert response.status_code == 403
    payload = json.loads(response.body.decode("utf-8"))
    assert payload["error_code"] == "READ_ONLY_DEMO"


def test_admin_can_still_run_when_needed(monkeypatch):
    _enable_demo(monkeypatch)

    response = _call_guard(_make_request("/api/run", method="POST", api_key="admin-key"))

    assert response.status_code == 200


def test_default_admin_key_is_rejected_in_read_only_demo(monkeypatch):
    _enable_demo(monkeypatch)
    monkeypatch.delenv("ARCBRIEF_API_KEY", raising=False)

    response = _call_guard(
        _make_request("/api/run", method="POST", api_key=m.DEFAULT_LOCAL_API_KEY)
    )

    assert response.status_code == 401


def test_demo_read_surfaces_are_public_only_when_enabled(monkeypatch):
    _enable_demo(monkeypatch)

    for path in (
        "/api/history",
        "/api/report/openai_035248",
        "/api/briefs/1/history",
        "/api/topics/1/articles",
        "/api/starter-packs",
        "/api/system/status",
        "/api/config",
        "/api/rss-health",
        "/api/report/openai_035248/export/pdf",
    ):
        assert _call_guard(_make_request(path)).status_code == 200, path

    monkeypatch.setattr(m, "PUBLIC_DEMO_READ_ONLY", False)

    assert _call_guard(_make_request("/api/history")).status_code == 401


def test_admin_writes_stay_protected_in_demo_mode(monkeypatch):
    _enable_demo(monkeypatch)

    response = _call_guard(
        _make_request("/api/topics", method="POST", api_key="guest-key")
    )

    assert response.status_code == 401
