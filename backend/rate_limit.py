"""Rate limit backends with Redis-first and in-memory fallback."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

try:
    import redis as _redis
except Exception:  # pragma: no cover - optional dependency
    _redis = None

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Simple sliding-window limiter for local development/testing."""

    def __init__(self) -> None:
        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, bucket_key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.time()
        threshold = now - max(1, window_seconds)
        with self._lock:
            self._buckets[bucket_key] = [t for t in self._buckets.get(bucket_key, []) if t > threshold]
            if len(self._buckets[bucket_key]) >= max(1, limit):
                return False
            self._buckets[bucket_key].append(now)
            return True


class RedisRateLimiter:
    """Redis-backed sliding-window limiter using ZSET + Lua for atomicity."""

    _SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window) + 2)
return 1
"""

    def __init__(self, storage_uri: str, prefix: str = "arcbrief:ratelimit", client=None) -> None:
        if not storage_uri:
            raise ValueError("storage_uri is required")
        if client is not None:
            self._client = client
        else:
            if _redis is None:
                raise RuntimeError("redis package is not installed")
            self._client = _redis.Redis.from_url(storage_uri, decode_responses=True)
            self._client.ping()
        self._prefix = prefix

    def allow(self, bucket_key: str, limit: int, window_seconds: int = 60) -> bool:
        key = f"{self._prefix}:{bucket_key}"
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        ok = self._client.eval(
            self._SCRIPT,
            1,
            key,
            str(now),
            str(max(1, window_seconds)),
            str(max(1, limit)),
            member,
        )
        return bool(ok)


class RateLimiter:
    """Redis-first limiter that gracefully degrades to memory on failures."""

    def __init__(self, storage_uri: str = "", prefix: str = "arcbrief:ratelimit") -> None:
        self._memory = InMemoryRateLimiter()
        self._redis: Optional[RedisRateLimiter] = None
        self._use_memory_only = True
        self.backend_name = "memory"
        uri = (storage_uri or "").strip()
        if uri:
            try:
                self._redis = RedisRateLimiter(uri, prefix=prefix)
                self._use_memory_only = False
                self.backend_name = "redis"
                logger.info("Rate limiter initialized with Redis backend.")
            except Exception as exc:  # pragma: no cover - depends on runtime infra
                logger.warning("Failed to initialize Redis rate limiter, fallback to memory: %s", exc)

    def allow(self, bucket_key: str, limit: int, window_seconds: int = 60) -> bool:
        if self._use_memory_only or self._redis is None:
            return self._memory.allow(bucket_key, limit, window_seconds=window_seconds)
        try:
            return self._redis.allow(bucket_key, limit, window_seconds=window_seconds)
        except Exception as exc:  # pragma: no cover - runtime fallback path
            logger.warning("Redis rate limiter unavailable, fallback to memory: %s", exc)
            self._use_memory_only = True
            self.backend_name = "memory"
            return self._memory.allow(bucket_key, limit, window_seconds=window_seconds)
