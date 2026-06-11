"""Redis Memory Manager — persistent session storage.

Architecture
------------
A module-level Redis connection pool is initialised at app startup.
Each LangGraph node creates a ``MemoryManager`` for the current session,
reads context before executing, and writes results afterwards.

Key design decisions
--------------------
- **Sync Redis client** — keeps LangGraph nodes synchronous (no async
  refactor needed).  For production at scale, swap to ``redis.asyncio``
  and make nodes ``async def``.
- **TTL on every write** — active sessions stay alive; idle sessions
  expire after ``SESSION_TTL_SECONDS``.
- **LRU caps via LTRIM** — lists are trimmed to a max length on every
  push so memory footprint stays bounded.
- **Graceful fallback** — if Redis is disabled or unreachable every
  method returns safe defaults (empty lists / None) instead of raising.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# ── Module-level connection pool ────────────────────────────────────────────
_pool: redis.ConnectionPool | None = None
_client: redis.Redis | None = None


def init_redis_pool(url: str | None = None) -> None:
    """Create the shared Redis connection pool.  Call once at startup."""
    global _pool, _client
    url = url or settings.redis_url
    _pool = redis.ConnectionPool.from_url(url, decode_responses=True)
    _client = redis.Redis(connection_pool=_pool)
    _client.ping()
    logger.info("Redis connected — %s", url)


def close_redis_pool() -> None:
    """Tear down the pool.  Call at shutdown."""
    global _pool, _client
    if _pool:
        _pool.disconnect()
        _pool = None
        _client = None
        logger.info("Redis disconnected")


def _get_client() -> redis.Redis | None:
    """Return the shared client, or None if Redis is disabled / uninitialised."""
    if not settings.redis_enabled:
        return None
    if _client is None:
        logger.warning("Redis pool not initialised — memory ops are no-ops")
    return _client


# ============================================================================
# MemoryManager
# ============================================================================


class MemoryManager:
    """Per-session read/write façade over Redis.

    Usage inside a LangGraph node::

        memory = MemoryManager(state["session_id"])
        ctx = memory.build_context()           # read before
        ...
        memory.save_plan(state["plan"])        # write after
        memory.add_message("ai", "...")
    """

    # ── Key prefixes ────────────────────────────────────────────────────

    def _k(self, suffix: str) -> str:
        return f"session:{self.session_id}:{suffix}"

    def __init__(self, session_id: str, client: redis.Redis | None = None) -> None:
        self.session_id = session_id
        self._r = client or _get_client()
        self._ttl = settings.session_ttl_seconds

    # ── Helpers ─────────────────────────────────────────────────────────

    def _push(self, key: str, data: dict, cap: int) -> None:
        """Push a JSON dict onto a list, trim, and refresh TTL."""
        if self._r is None:
            return
        payload = json.dumps(data, ensure_ascii=False)
        pipe = self._r.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -cap, -1)
        pipe.expire(key, self._ttl)
        pipe.execute()

    def _peek(self, key: str, index: int = -1) -> dict | None:
        """Return the element at *index* as a dict, or None."""
        if self._r is None:
            return None
        raw = self._r.lindex(key, index)
        return json.loads(raw) if raw else None

    def _range(self, key: str, start: int, end: int) -> list[dict]:
        """Return a slice of the list as dicts."""
        if self._r is None:
            return []
        return [json.loads(m) for m in self._r.lrange(key, start, end)]

    # ── Messages ────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str, agent: str = "") -> None:
        """Append a conversation message."""
        self._push(
            self._k("messages"),
            {
                "role": role,
                "agent": agent,
                "content": content,
                "timestamp": time.time(),
            },
            cap=settings.max_messages_per_session,
        )

    def get_messages(self, limit: int = 20) -> list[dict]:
        """Return the *limit* most recent messages."""
        return self._range(self._k("messages"), -limit, -1)

    # ── Plan history ────────────────────────────────────────────────────

    def save_plan(self, plan: str) -> None:
        """Persist a plan version."""
        self._push(
            self._k("plan_history"),
            {
                "plan": plan,
                "timestamp": time.time(),
                "version": self._count(self._k("plan_history")) + 1,
            },
            cap=settings.max_plan_history,
        )
        self._hset_state("current_plan", plan)

    def get_latest_plan(self) -> str | None:
        """Return the most recent plan, or None."""
        entry = self._peek(self._k("plan_history"))
        return entry["plan"] if entry else None

    def get_plan_history(self, limit: int = 5) -> list[dict]:
        """Return the last *limit* plans."""
        return self._range(self._k("plan_history"), -limit, -1)

    # ── Code history ────────────────────────────────────────────────────

    def save_code(self, code: str, trigger: str = "initial") -> None:
        """Persist a code version.

        Args:
            code: The generated code string.
            trigger: Why this version was created —
                     ``"initial"`` | ``"auto_fix"`` | ``"human_fix"``.
        """
        self._push(
            self._k("code_history"),
            {
                "code": code,
                "trigger": trigger,
                "timestamp": time.time(),
                "version": self._count(self._k("code_history")) + 1,
            },
            cap=settings.max_code_history,
        )
        self._hset_state("current_code", code)

    def get_latest_code(self) -> str | None:
        """Return the most recent code, or None."""
        entry = self._peek(self._k("code_history"))
        return entry["code"] if entry else None

    def get_code_history(self, limit: int = 10) -> list[dict]:
        """Return the last *limit* code versions (metadata only, no code body)."""
        entries = self._range(self._k("code_history"), -limit, -1)
        # Return metadata without the full code body for list views
        return [
            {
                "version": e.get("version"),
                "trigger": e.get("trigger"),
                "timestamp": e.get("timestamp"),
                "code_preview": e.get("code", "")[:200],
            }
            for e in entries
        ]

    def get_code_versions_count(self) -> int:
        """How many code versions exist for this session."""
        return self._count(self._k("code_history"))

    # ── Review history ──────────────────────────────────────────────────

    def save_review(self, review: dict, iteration: int) -> None:
        """Persist a review verdict."""
        self._push(
            self._k("review_history"),
            {
                "passed": review.get("passed", False),
                "issues": review.get("issues", []),
                "iteration": iteration,
                "timestamp": time.time(),
            },
            cap=settings.max_review_history,
        )
        self._hset_state("current_review", json.dumps(review, ensure_ascii=False))

    def get_latest_review(self) -> dict | None:
        """Return the most recent review verdict."""
        return self._peek(self._k("review_history"))

    def get_review_history(self, limit: int = 10) -> list[dict]:
        """Return the last *limit* review records."""
        return self._range(self._k("review_history"), -limit, -1)

    # ── Session state & metadata ────────────────────────────────────────

    def update_metadata(self, **kwargs: Any) -> None:
        """Set arbitrary metadata fields for the session."""
        if self._r is None:
            return
        key = self._k("metadata")
        self._r.hset(key, mapping={k: str(v) for k, v in kwargs.items()})
        self._r.expire(key, self._ttl)

    def get_metadata(self) -> dict[str, str]:
        """Return all session metadata."""
        if self._r is None:
            return {}
        return self._r.hgetall(self._k("metadata"))

    def get_state_snapshot(self) -> dict[str, str]:
        """Return the lightweight state hash."""
        if self._r is None:
            return {}
        return self._r.hgetall(self._k("state"))

    def set_status(self, status: str) -> None:
        """Update the session status (``"running"`` | ``"paused"`` | ``"completed"``)."""
        self._hset_state("status", status)
        self.update_metadata(last_status=status, last_active=str(time.time()))

    # ── Context assembly (called before each agent node) ────────────────

    def build_context(self) -> dict:
        """Assemble a context dictionary for the agent.

        This is called at the **start** of every agent node so the mock
        (or real) LLM can condition on prior history.
        """
        return {
            "recent_messages": self.get_messages(limit=20),
            "latest_plan": self.get_latest_plan(),
            "latest_code": self.get_latest_code(),
            "latest_review": self.get_latest_review(),
            "code_version_count": self.get_code_versions_count(),
            "metadata": self.get_metadata(),
        }

    def get_memory_stats(self) -> dict:
        """Return statistics about this session's memory usage."""
        if self._r is None:
            return {"redis_enabled": False}
        return {
            "redis_enabled": True,
            "messages_count": self._count(self._k("messages")),
            "plan_versions": self._count(self._k("plan_history")),
            "code_versions": self._count(self._k("code_history")),
            "review_count": self._count(self._k("review_history")),
        }

    # ── Internal helpers ────────────────────────────────────────────────

    def _hset_state(self, field: str, value: str) -> None:
        """Set a single field in the state hash."""
        if self._r is None:
            return
        key = self._k("state")
        self._r.hset(key, field, value)
        self._r.expire(key, self._ttl)

    def _count(self, key: str) -> int:
        """Return the length of a list key (0 if missing)."""
        if self._r is None:
            return 0
        return self._r.llen(key)
