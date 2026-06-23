"""Async Redis connection pool — shared by MemoryManager and RedisSaver.

Usage::

    from app.redis_client import init_async_redis, close_async_redis, get_async_redis

    await init_async_redis()
    client = get_async_redis()
    await client.set("foo", "bar")
    await close_async_redis()

Health check
------------
:func:`check_redis_health` performs a lightweight ``PING`` and returns
``(healthy: bool, latency_ms: float)``.  Callers can use this to decide
whether to fall back to in-memory storage.
"""

from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None
_healthy: bool = False
_last_health_check: float = 0.0


async def init_async_redis(url: str | None = None) -> None:
    """Create the shared async Redis connection pool.  Call once at startup."""
    global _pool, _client, _healthy
    url = url or settings.redis_url
    _pool = aioredis.ConnectionPool.from_url(url, decode_responses=False)
    _client = aioredis.Redis(connection_pool=_pool)
    await _client.ping()
    _healthy = True
    logger.info("Async Redis connected — %s", url)


async def close_async_redis() -> None:
    """Tear down the pool.  Call at shutdown."""
    global _pool, _client, _healthy
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.disconnect()
    _pool = None
    _client = None
    _healthy = False
    logger.info("Async Redis disconnected")


def get_async_redis() -> aioredis.Redis | None:
    """Return the shared async client, or None if Redis is disabled / uninitialised."""
    if not settings.redis_enabled:
        return None
    if _client is None:
        logger.warning("Async Redis pool not initialised — Redis ops will be no-ops")
    return _client


async def check_redis_health() -> tuple[bool, float]:
    """Check whether Redis is reachable via ``PING``.

    Returns:
        ``(healthy: bool, latency_ms: float)`` — latency is 0.0 when unhealthy.
    """
    global _healthy, _last_health_check
    if not settings.redis_enabled:
        return False, 0.0

    r = get_async_redis()
    if r is None:
        _healthy = False
        return False, 0.0

    t0 = time.perf_counter()
    try:
        await r.ping()
        latency = (time.perf_counter() - t0) * 1000
        _healthy = True
        _last_health_check = time.time()
        return True, latency
    except Exception as exc:
        _healthy = False
        latency = (time.perf_counter() - t0) * 1000
        logger.warning("Redis health check failed: %s", exc)
        return False, latency


def is_redis_healthy() -> bool:
    """Return the cached health status (no network call)."""
    return _healthy and settings.redis_enabled


async def reconnect_redis() -> bool:
    """Attempt to re-establish the Redis connection after a failure.

    Returns ``True`` if the reconnection succeeded.
    """
    global _client, _pool, _healthy
    try:
        # Close any stale connection
        if _client:
            try:
                await _client.aclose()
            except Exception:
                pass
        if _pool:
            try:
                await _pool.disconnect()
            except Exception:
                pass

        # Recreate pool and client
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url, decode_responses=False
        )
        _client = aioredis.Redis(connection_pool=_pool)
        await _client.ping()
        _healthy = True
        logger.info("Redis reconnected successfully")
        return True
    except Exception as exc:
        _healthy = False
        _client = None
        _pool = None
        logger.error("Redis reconnection failed: %s", exc)
        return False
