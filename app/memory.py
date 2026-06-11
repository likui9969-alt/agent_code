"""Redis Memory Manager — persistent session storage (async).

Architecture
------------
A module-level async Redis connection pool is initialised at app startup.
Each LangGraph node creates a ``MemoryManager`` for the current session,
reads context before executing, and writes results afterwards.

Key design decisions
--------------------
- **Async Redis client** — uses ``redis.asyncio`` so Redis I/O never blocks
  the FastAPI event loop.  LangGraph nodes are ``async def``.
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

from app.config import settings
from app.redis_client import get_async_redis

logger = logging.getLogger(__name__)


# ============================================================================
# MemoryManager
# ============================================================================


class MemoryManager:
    """Per-session read/write façade over async Redis.

    Usage inside an async LangGraph node::

        memory = MemoryManager(state["session_id"])
        ctx = await memory.build_context()           # read before
        ...
        await memory.save_plan(state["plan"])        # write after
        await memory.add_message("ai", "...")
    """

    # ── Key prefixes ────────────────────────────────────────────────────

    def _k(self, suffix: str) -> str:
        return f"session:{self.session_id}:{suffix}"

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._ttl = settings.session_ttl_seconds

    @property
    def _r(self):
        """Lazy reference to the shared async Redis client."""
        return get_async_redis()

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _push(self, key: str, data: dict, cap: int) -> None:
        """Push a JSON dict onto a list, trim, and refresh TTL."""
        r = self._r
        if r is None:
            return
        payload = json.dumps(data, ensure_ascii=False)
        async with r.client() as conn:
            await conn.rpush(key, payload)
            await conn.ltrim(key, -cap, -1)
            await conn.expire(key, self._ttl)

    async def _peek(self, key: str, index: int = -1) -> dict | None:
        """Return the element at *index* as a dict, or None."""
        r = self._r
        if r is None:
            return None
        raw = await r.lindex(key, index)
        return json.loads(raw) if raw else None

    async def _range(self, key: str, start: int, end: int) -> list[dict]:
        """Return a slice of the list as dicts."""
        r = self._r
        if r is None:
            return []
        items = await r.lrange(key, start, end)
        return [json.loads(m) for m in items]

    # ── Messages ────────────────────────────────────────────────────────

    async def add_message(self, role: str, content: str, agent: str = "") -> None:
        """Append a conversation message."""
        await self._push(
            self._k("messages"),
            {
                "role": role,
                "agent": agent,
                "content": content,
                "timestamp": time.time(),
            },
            cap=settings.max_messages_per_session,
        )

    async def get_messages(self, limit: int = 20) -> list[dict]:
        """Return the *limit* most recent messages."""
        return await self._range(self._k("messages"), -limit, -1)

    # ── Plan history ────────────────────────────────────────────────────

    async def save_plan(self, plan: str) -> None:
        """Persist a plan version."""
        await self._push(
            self._k("plan_history"),
            {
                "plan": plan,
                "timestamp": time.time(),
                "version": await self._count(self._k("plan_history")) + 1,
            },
            cap=settings.max_plan_history,
        )
        await self._hset_state("current_plan", plan)

    async def get_latest_plan(self) -> str | None:
        """Return the most recent plan, or None."""
        entry = await self._peek(self._k("plan_history"))
        return entry["plan"] if entry else None

    async def get_plan_history(self, limit: int = 5) -> list[dict]:
        """Return the last *limit* plans."""
        return await self._range(self._k("plan_history"), -limit, -1)

    # ── Code history ────────────────────────────────────────────────────

    async def save_code(self, code: str, trigger: str = "initial") -> None:
        """Persist a code version.

        Args:
            code: The generated code string.
            trigger: Why this version was created —
                     ``"initial"`` | ``"auto_fix"`` | ``"human_fix"``.
        """
        await self._push(
            self._k("code_history"),
            {
                "code": code,
                "trigger": trigger,
                "timestamp": time.time(),
                "version": await self._count(self._k("code_history")) + 1,
            },
            cap=settings.max_code_history,
        )
        await self._hset_state("current_code", code)

    async def get_latest_code(self) -> str | None:
        """Return the most recent code, or None."""
        entry = await self._peek(self._k("code_history"))
        return entry["code"] if entry else None

    async def get_code_history(self, limit: int = 10) -> list[dict]:
        """Return the last *limit* code versions (metadata only, no code body)."""
        entries = await self._range(self._k("code_history"), -limit, -1)
        return [
            {
                "version": e.get("version"),
                "trigger": e.get("trigger"),
                "timestamp": e.get("timestamp"),
                "code_preview": e.get("code", "")[:200],
            }
            for e in entries
        ]

    async def get_code_versions_count(self) -> int:
        """How many code versions exist for this session."""
        return await self._count(self._k("code_history"))

    # ── Review history ──────────────────────────────────────────────────

    async def save_review(self, review: dict, iteration: int) -> None:
        """Persist a review verdict."""
        await self._push(
            self._k("review_history"),
            {
                "passed": review.get("passed", False),
                "issues": review.get("issues", []),
                "iteration": iteration,
                "timestamp": time.time(),
            },
            cap=settings.max_review_history,
        )
        await self._hset_state("current_review", json.dumps(review, ensure_ascii=False))

    async def get_latest_review(self) -> dict | None:
        """Return the most recent review verdict."""
        return await self._peek(self._k("review_history"))

    async def get_review_history(self, limit: int = 10) -> list[dict]:
        """Return the last *limit* review records."""
        return await self._range(self._k("review_history"), -limit, -1)

    # ── Session state & metadata ────────────────────────────────────────

    async def update_metadata(self, **kwargs: Any) -> None:
        """Set arbitrary metadata fields for the session."""
        r = self._r
        if r is None:
            return
        key = self._k("metadata")
        async with r.client() as conn:
            await conn.hset(key, mapping={k: str(v) for k, v in kwargs.items()})
            await conn.expire(key, self._ttl)

    async def get_metadata(self) -> dict[str, str]:
        """Return all session metadata."""
        r = self._r
        if r is None:
            return {}
        raw = await r.hgetall(self._k("metadata"))
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in raw.items()}

    async def get_state_snapshot(self) -> dict[str, str]:
        """Return the lightweight state hash."""
        r = self._r
        if r is None:
            return {}
        raw = await r.hgetall(self._k("state"))
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in raw.items()}

    async def set_status(self, status: str) -> None:
        """Update the session status (``"running"`` | ``"paused"`` | ``"completed"``)."""
        await self._hset_state("status", status)
        await self.update_metadata(last_status=status, last_active=str(time.time()))

    # ── Context assembly (called before each agent node) ────────────────

    async def build_context(self) -> dict:
        """Assemble a context dictionary for the agent.

        This is called at the **start** of every agent node so the
        LLM can condition on prior history.
        """
        return {
            "recent_messages": await self.get_messages(limit=20),
            "latest_plan": await self.get_latest_plan(),
            "latest_code": await self.get_latest_code(),
            "latest_review": await self.get_latest_review(),
            "code_version_count": await self.get_code_versions_count(),
            "metadata": await self.get_metadata(),
        }

    async def get_memory_stats(self) -> dict:
        """Return statistics about this session's memory usage."""
        r = self._r
        if r is None:
            return {"redis_enabled": False}
        return {
            "redis_enabled": True,
            "messages_count": await self._count(self._k("messages")),
            "plan_versions": await self._count(self._k("plan_history")),
            "code_versions": await self._count(self._k("code_history")),
            "review_count": await self._count(self._k("review_history")),
        }

    # ── Internal helpers ────────────────────────────────────────────────

    async def _hset_state(self, field: str, value: str) -> None:
        """Set a single field in the state hash."""
        r = self._r
        if r is None:
            return
        key = self._k("state")
        async with r.client() as conn:
            await conn.hset(key, field, value)
            await conn.expire(key, self._ttl)

    async def _count(self, key: str) -> int:
        """Return the length of a list key (0 if missing)."""
        r = self._r
        if r is None:
            return 0
        return await r.llen(key)
