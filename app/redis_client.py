"""Async Redis connection pool — shared by MemoryManager and RedisSaver.

Usage::

    from app.redis_client import init_async_redis, close_async_redis, get_async_redis

    await init_async_redis()
    client = get_async_redis()
    await client.set("foo", "bar")
    await close_async_redis()
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def init_async_redis(url: str | None = None) -> None:
    """Create the shared async Redis connection pool.  Call once at startup."""
    global _pool, _client
    url = url or settings.redis_url
    _pool = aioredis.ConnectionPool.from_url(url, decode_responses=False)
    _client = aioredis.Redis(connection_pool=_pool)
    await _client.ping()
    logger.info("Async Redis connected — %s", url)


async def close_async_redis() -> None:
    """Tear down the pool.  Call at shutdown."""
    global _pool, _client
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.disconnect()
    _pool = None
    _client = None
    logger.info("Async Redis disconnected")


def get_async_redis() -> aioredis.Redis | None:
    """Return the shared async client, or None if Redis is disabled / uninitialised."""
    if not settings.redis_enabled:
        return None
    if _client is None:
        logger.warning("Async Redis pool not initialised — Redis ops will be no-ops")
    return _client
