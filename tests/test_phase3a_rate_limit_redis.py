"""Tests for Redis-backed rate limit behavior and fallback."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.rate_limit as rl


class _FakeRedisClient:
    def __init__(self):
        self._buckets = {}

    def eval(self, _script, _keys, key, now_s, window_s, limit_s, _member):
        now = float(now_s)
        window = max(1, int(float(window_s)))
        limit = max(1, int(float(limit_s)))
        threshold = now - window
        values = [t for t in self._buckets.get(key, []) if t > threshold]
        self._buckets[key] = values
        if len(values) >= limit:
            return 0
        values.append(now)
        self._buckets[key] = values
        return 1


def test_redis_rate_limiter_enforces_limit():
    limiter = rl.RedisRateLimiter("redis://unused", client=_FakeRedisClient())
    key = "global:guest:abc123"
    assert limiter.allow(key, 2) is True
    assert limiter.allow(key, 2) is True
    assert limiter.allow(key, 2) is False


def test_rate_limiter_falls_back_to_memory_when_redis_init_fails(monkeypatch):
    class _BrokenRedisRateLimiter:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(rl, "RedisRateLimiter", _BrokenRedisRateLimiter)
    limiter = rl.RateLimiter("redis://broken")
    assert limiter.backend_name == "memory"
    assert limiter.allow("bucket:a", 1) is True
    assert limiter.allow("bucket:a", 1) is False
