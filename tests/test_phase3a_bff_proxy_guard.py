"""Static guard checks for BFF proxy security policy.

These tests read the BFF route.ts source and verify structural invariants
(allowlists, route classification, key injection) via string assertions.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROUTE_FILE = Path("frontend/app/api/proxy/[...path]/route.ts")


def _route_source() -> str:
    return ROUTE_FILE.read_text(encoding="utf-8")


def _classify_route_body() -> str:
    match = re.search(r"function classifyRoute\(.*?\n\}", _route_source(), re.S)
    assert match, "classifyRoute must exist at top level"
    return match.group(0)


def test_bff_has_allowlist_for_public_get_and_guest_post():
    """Public GET and guest POST allowlists are defined."""
    src = _route_source()
    assert "PUBLIC_GET_ALLOWLIST" in src
    assert "/health" in src
    assert "/topics" in src
    assert "/briefs\\/recent" in src
    assert "/briefs\\/\\d+\\/export" in src
    assert "GUEST_POST_ALLOWLIST" in src
    assert "/run" in src
    assert "/chat" in src


def test_bff_uses_classify_route_for_access_control():
    """classifyRoute determines route kind; forbidden routes are rejected."""
    src = _route_source()
    assert "classifyRoute(method, path)" in src
    assert "RouteKind" in src
    assert "'public_get'" in src
    assert "'guest_post'" in src
    assert "'admin'" in src
    assert "'forbidden'" in src
    assert "PROXY_FORBIDDEN" in src
    assert "forbiddenResponse()" in src


def test_bff_injects_keys_by_route_kind():
    """Guest POST injects GUEST_API_KEY; admin injects ADMIN_API_KEY; no user-supplied key forwarded."""
    src = _route_source()
    assert "headers.set('X-API-Key', GUEST_API_KEY)" in src
    assert "headers.set('X-API-Key', ADMIN_API_KEY)" in src
    assert "request.headers.get('x-api-key')" not in src.lower()


def test_bff_admin_key_gated_by_env_var():
    """Admin routes only open when ARCBRIEF_PROXY_ADMIN_KEY is configured."""
    src = _route_source()
    assert "ARCBRIEF_PROXY_ADMIN_KEY" in src
    assert "ADMIN_API_KEY" in src
    classify = _classify_route_body()
    assert "ADMIN_API_KEY" in classify and "'admin'" in classify


def test_bff_read_only_mode_flag_and_allowlist():
    """Read-only demo exposes extra GET surfaces and its own allowlist."""
    src = _route_source()
    assert "ARCBRIEF_PUBLIC_READ_ONLY" in src
    assert "READ_ONLY_GET_ALLOWLIST" in src
    for pattern in ("\\/history", "\\/report\\/", "\\/starter-packs", "\\/system\\/status", "\\/config", "\\/rss-health"):
        assert pattern in src, pattern
    assert "READ_ONLY_DEMO" in src
    assert "readOnlyResponse()" in src


def test_bff_read_only_blocks_guest_and_admin_writes():
    """When read-only, guest POST is not classified and admin key is never attached."""
    src = _route_source()
    classify = _classify_route_body()
    assert "!READ_ONLY && method === 'POST'" in classify
    assert "!READ_ONLY && ADMIN_API_KEY" in classify
    assert "if (READ_ONLY && method === 'POST') return readOnlyResponse();" in src
