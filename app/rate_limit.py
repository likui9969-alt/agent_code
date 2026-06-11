"""API Rate Limiter — sliding window (Redis) + fixed window (in-memory fallback).

Algorithm
---------
**Redis**: sliding window via sorted set (ZSET).  Each request is added as a
member whose score is the current timestamp in milliseconds.  Before checking,
members older than ``window_seconds`` are evicted via ``ZREMRANGEBYSCORE``.
The count of remaining members is the current request rate.  This is precise
to the millisecond and avoids the burst-at-boundary problem of fixed windows.

**In-memory fallback**: simple fixed window with a ``threading.Lock`` guard.
Less precise at window boundaries, but keeps the app functional when Redis is
unavailable.

Client identification
---------------------
1. Authenticated requests → SHA-256 hash of the Bearer token (first 16 hex
   chars).  This gives per-user fairness without storing the raw token.
2. Unauthenticated requests → ``X-Forwarded-For`` header (if behind a proxy)
   or ``request.client.host`` (direct IP).

Perf note
---------
Each rate-limit check costs 3 Redis round-trips (ZREMRANGEBYSCORE, ZCARD,
ZADD + EXPIRE).  With a local Redis instance this is ~0.5–1 ms.  The sorted
set is automatically cleaned by the eviction in step 1, so storage is bounded
by ``max_requests`` entries per client.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.redis_client import get_async_redis

logger = logging.getLogger(__name__)

# ── Exempt paths (never rate-limited) ────────────────────────────────────────
_EXEMPT_PATHS: frozenset[str] = frozenset({"/health"})


# ============================================================================
# RateLimiter core
# ============================================================================


class RateLimiter:
    """Sliding-window rate limiter backed by Redis (with in-memory fallback)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        # ── In-memory fallback state ──────────────────────────────────
        self._memory: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────

    async def is_allowed(self, client_id: str) -> tuple[bool, int]:
        """Check whether *client_id* is allowed to make a request.

        Returns:
            ``(allowed: bool, remaining: int)`` — *remaining* is the number
            of requests the client can still make in the current window
            (0 when disallowed).
        """
        redis = get_async_redis()
        if redis is not None:
            return await self._check_redis(redis, client_id)
        return self._check_memory(client_id)

    # ── Redis sliding window ──────────────────────────────────────────────

    async def _check_redis(self, redis, client_id: str) -> tuple[bool, int]:
        key = f"ratelimit:{client_id}"
        now_ms = int(time.time() * 1000)
        window_ms = self.window_seconds * 1000
        window_start = now_ms - window_ms

        async with redis.client() as conn:
            # 1. Evict entries outside the window
            await conn.zremrangebyscore(key, 0, window_start)

            # 2. Count remaining
            count = await conn.zcard(key)

            if count >= self.max_requests:
                return False, 0

            # 3. Add current request (use a unique member to avoid overwrites
            #    when multiple requests land on the same millisecond)
            member = f"{now_ms}:{count}"
            await conn.zadd(key, {member: now_ms})
            await conn.expire(key, self.window_seconds + 1)

            return True, self.max_requests - count - 1

    # ── In-memory fixed window (fallback) ─────────────────────────────────

    def _check_memory(self, client_id: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            window_start, count = self._memory.get(client_id, (0.0, 0))

            # Reset if window expired
            if now - window_start > self.window_seconds:
                window_start = now
                count = 0

            if count >= self.max_requests:
                return False, 0

            count += 1
            self._memory[client_id] = (window_start, count)
            return True, self.max_requests - count

    # ── Housekeeping ──────────────────────────────────────────────────────

    def cleanup_memory(self) -> None:
        """Remove expired entries from the in-memory store.

        Call periodically (e.g. every 60 s) to prevent unbounded growth
        when the in-memory fallback is active.
        """
        now = time.time()
        with self._lock:
            expired = [
                cid for cid, (ws, _) in self._memory.items()
                if now - ws > self.window_seconds * 2
            ]
            for cid in expired:
                del self._memory[cid]


# ============================================================================
# Client identification helper
# ============================================================================


def _get_client_id(request: Request) -> str:
    """Extract a stable client identifier from the request.

    Precedence:
        1. SHA-256 hash of the Bearer token (per-user fairness).
        2. ``X-Forwarded-For`` header (for proxied deployments).
        3. Direct client IP.
    """
    # ── Authenticated: hash the token (never store raw token in Redis keys) ─
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
        return f"auth:{token_hash}"

    # ── IP-based ─────────────────────────────────────────────────────────
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


# ============================================================================
# FastAPI / Starlette middleware
# ============================================================================


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-client rate limits.

    Attributes:
        limiter: The :class:`RateLimiter` instance.
        exempt: Set of path prefixes that skip rate-limiting (e.g. ``/health``).
    """

    def __init__(self, app, limiter: RateLimiter, exempt: frozenset[str] = _EXEMPT_PATHS):
        super().__init__(app)
        self.limiter = limiter
        self.exempt = exempt

    async def dispatch(self, request: Request, call_next):
        # ── Skip exempt paths ─────────────────────────────────────────
        if request.url.path in self.exempt:
            return await call_next(request)

        # ── Skip OPTIONS preflight (CORS handles it) ──────────────────
        if request.method == "OPTIONS":
            return await call_next(request)

        # ── Rate-limit check ──────────────────────────────────────────
        client_id = _get_client_id(request)
        allowed, remaining = await self.limiter.is_allowed(client_id)

        if not allowed:
            logger.warning(
                "Rate limit exceeded — client=%s path=%s",
                client_id, request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "error": (
                        f"Rate limit exceeded: {self.limiter.max_requests} "
                        f"requests per {self.limiter.window_seconds}s. "
                        f"Retry later."
                    ),
                },
                headers={
                    "Retry-After": str(self.limiter.window_seconds),
                    "X-RateLimit-Limit": str(self.limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ============================================================================
# Module-level singleton (bound lazily to avoid import-side-effects)
# ============================================================================

_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the singleton :class:`RateLimiter`, creating it on first call."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        logger.info(
            "Rate limiter initialised — %d req / %d s",
            _limiter.max_requests, _limiter.window_seconds,
        )
    return _limiter
