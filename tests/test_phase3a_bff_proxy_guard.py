"""Static guard checks for BFF proxy security policy.

These tests read the BFF route.ts source and verify structural invariants
(allowlists, route classification, key injection) via string assertions.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROUTE_FILE = Path("frontend/app/api/proxy/[...path]/route.ts")


def _route_source() -> str:
    return ROUTE_FILE.read_text(encoding="utf-8")


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
    # classifyRoute must check ADMIN_API_KEY before returning 'admin'
    lines = [l.strip() for l in src.splitlines()]
    in_classify = False
    found_admin_check = False
    for line in lines:
        if "function classifyRoute" in line:
            in_classify = True
        if in_classify and "ADMIN_API_KEY" in line and "'admin'" in line:
            found_admin_check = True
        if in_classify and line.startswith("}"):
            break
    assert found_admin_check, "classifyRoute must check ADMIN_API_KEY before returning 'admin'"
