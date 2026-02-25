"""Tests for rate limiting helpers (Phase 3A)."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m


def test_allows_up_to_limit():
    key = f"test_limit_{time.time_ns()}"
    for _ in range(3):
        assert m._check_rate_limit(key, 3) is True
    assert m._check_rate_limit(key, 3) is False  # 4th request blocked


def test_different_keys_isolated():
    ts = time.time_ns()
    key_a, key_b = f"key_a_{ts}", f"key_b_{ts}"
    for _ in range(3):
        m._check_rate_limit(key_a, 3)
    assert m._check_rate_limit(key_b, 3) is True


def test_route_rate_limit_delegates():
    ts = time.time_ns()
    route = f"/api/run_{ts}"
    for _ in range(2):
        assert m._check_route_rate_limit(route, "ip1", 2) is True
    assert m._check_route_rate_limit(route, "ip1", 2) is False


def test_route_rate_limit_isolates_identities():
    ts = time.time_ns()
    route = f"/api/run_{ts}"
    for _ in range(2):
        m._check_route_rate_limit(route, "ip1", 2)
    # ip2 has its own bucket and should still pass
    assert m._check_route_rate_limit(route, "ip2", 2) is True

