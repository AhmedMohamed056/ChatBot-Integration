"""Optional Redis client (noop when REDIS_URL is unset)."""

from __future__ import annotations

import os
from typing import Optional

_redis = None


def get_redis():
    global _redis
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    if _redis is None:
        import redis

        _redis = redis.from_url(url, decode_responses=True)
    return _redis


def cache_get(key: str) -> Optional[str]:
    client = get_redis()
    if not client:
        return None
    return client.get(key)


def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    client = get_redis()
    if not client:
        return
    client.setex(key, ttl_seconds, value)
