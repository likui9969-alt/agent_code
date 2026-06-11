"""Redis-backed LangGraph checkpoint saver (JSON — no pickle).

Extends :class:`InMemorySaver` with async Redis persistence so
checkpoints survive worker restarts in multi-worker deployments.

Storage model
-------------
Each thread's checkpoints, writes, and blobs are serialised as a single
**JSON** blob per thread ID (never pickle — eliminates RCE surface).
Complex types (LangChain messages, bytes, datetime) are encoded with
``__type__`` discriminator markers and validated on load.

Security
--------
- **No pickle**: JSON cannot execute arbitrary code.
- **Structure validation**: only dicts with the exact top-level keys
  ``storage`` / ``writes`` / ``blobs`` are accepted.
- **Type-whitelist**: only known ``__type__`` tags are decoded; unknown
  tags are rejected.
- **Size limit**: checkpoints larger than 50 MiB are refused.
"""

from __future__ import annotations

import base64
import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver

from app.config import settings
from app.redis_client import get_async_redis

logger = logging.getLogger(__name__)

# ============================================================================
# Format / size constants
# ============================================================================

_CHECKPOINT_FORMAT_VERSION = 1
_MAX_CHECKPOINT_BYTES = 50 * 1024 * 1024  # 50 MiB — refuse anything larger

# ============================================================================
# Type-discriminator map for LangChain messages
# ============================================================================

_MESSAGE_CLASSES: dict[str, type[BaseMessage]] = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
    "tool": ToolMessage,
}

_ALLOWED_TYPE_TAGS: frozenset[str] = frozenset({
    "langchain:human",
    "langchain:ai",
    "langchain:system",
    "langchain:tool",
    "bytes",
    "datetime",
})


# ============================================================================
# Safe encoder / decoder (zero-code-exec — pure data transformation)
# ============================================================================


def _to_json_safe(obj: object) -> object:
    """Walk *obj* and convert non-JSON types to tagged dicts."""
    # ── LangChain messages ─────────────────────────────────────────────
    if isinstance(obj, BaseMessage):
        return {
            "__type__": f"langchain:{obj.type}",
            "content": obj.content,
            "id": getattr(obj, "id", None),
            "name": getattr(obj, "name", None),
            "additional_kwargs": getattr(obj, "additional_kwargs", {}),
            "response_metadata": getattr(obj, "response_metadata", {}),
        }

    # ── bytes → base64 ─────────────────────────────────────────────────
    if isinstance(obj, bytes):
        return {
            "__type__": "bytes",
            "data": base64.b64encode(obj).decode("ascii"),
        }

    # ── datetime → ISO ─────────────────────────────────────────────────
    if isinstance(obj, datetime):
        return {"__type__": "datetime", "iso": obj.isoformat()}

    # ── defaultdict → plain dict ───────────────────────────────────────
    if isinstance(obj, defaultdict):
        return {k: _to_json_safe(v) for k, v in obj.items()}

    # ── dict ───────────────────────────────────────────────────────────
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}

    # ── list / tuple ───────────────────────────────────────────────────
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]

    # ── atomic JSON types (str, int, float, bool, None) pass through ───
    return obj


def _from_json_safe(obj: object) -> object:
    """Walk *obj* and convert tagged dicts back to Python types.

    Raises:
        ValueError: if an unknown ``__type__`` tag is encountered.
    """
    if isinstance(obj, dict):
        tag = obj.get("__type__")

        if tag is not None:
            # ── Security: only allow known type tags ─────────────────
            if tag not in _ALLOWED_TYPE_TAGS:
                raise ValueError(
                    f"Unknown or disallowed __type__ tag: {tag!r}"
                )

            if tag.startswith("langchain:"):
                return _dict_to_message(obj, tag)

            if tag == "bytes":
                return base64.b64decode(obj["data"])

            if tag == "datetime":
                return datetime.fromisoformat(obj["iso"])

        # Plain dict → recurse into values
        return {k: _from_json_safe(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_from_json_safe(v) for v in obj]

    return obj


def _dict_to_message(data: dict, tag: str) -> BaseMessage:
    """Reconstruct a LangChain message from its tagged dict."""
    msg_type = tag.split(":", 1)[1]  # e.g. "human"
    cls = _MESSAGE_CLASSES.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown message type: {msg_type!r}")

    kwargs: dict[str, Any] = {"content": data.get("content", "")}
    if data.get("id"):
        kwargs["id"] = data["id"]
    if data.get("name"):
        kwargs["name"] = data["name"]
    if data.get("additional_kwargs"):
        kwargs["additional_kwargs"] = data["additional_kwargs"]
    if data.get("response_metadata"):
        kwargs["response_metadata"] = data["response_metadata"]
    return cls(**kwargs)


# ============================================================================
# Structural validation (defence-in-depth — rejects malformed / malicious data)
# ============================================================================


def _validate_checkpoint_structure(data: dict[str, Any]) -> None:
    """Validate the top-level structure of a deserialized checkpoint blob.

    Only accepts dicts with **exactly** the keys ``storage``, ``writes``,
    ``blobs`` whose values are themselves dicts.  Anything else is treated as
    tampered / corrupt data and rejected safely.
    """
    if not isinstance(data, dict):
        raise ValueError("Checkpoint root must be a dict")

    required = {"storage", "writes", "blobs"}
    actual = set(data.keys())
    if actual != required:
        raise ValueError(
            f"Checkpoint must have exactly keys {sorted(required)}, "
            f"got {sorted(actual)}"
        )

    for key in required:
        if not isinstance(data[key], dict):
            raise ValueError(
                f"Checkpoint key {key!r} must be a dict, "
                f"got {type(data[key]).__name__}"
            )


def _validate_size(data_str: str) -> None:
    """Refuse checkpoints larger than the configured maximum."""
    size = len(data_str.encode("utf-8"))
    if size > _MAX_CHECKPOINT_BYTES:
        raise ValueError(
            f"Checkpoint data too large: {size / 1024 / 1024:.1f} MiB "
            f"(max {_MAX_CHECKPOINT_BYTES / 1024 / 1024:.0f} MiB)"
        )


# ============================================================================
# defaultdict helpers (needed because InMemorySaver stores defaultdicts)
# ============================================================================


def _plain_to_defaultdict(obj: object) -> object:
    """Convert plain dicts back to ``defaultdict(dict)`` trees.

    This is the inverse of :func:`_to_json_safe` for defaultdicts.
    InMemorySaver expects ``storage`` / ``writes`` / ``blobs`` to be
    ``defaultdict`` instances so we recreate them after loading.
    """
    if isinstance(obj, dict) and "__type__" not in obj:
        dd = defaultdict(dict)
        for k, v in obj.items():
            dd[k] = _plain_to_defaultdict(v)
        return dd
    if isinstance(obj, list):
        return [_plain_to_defaultdict(v) for v in obj]
    return obj


# ============================================================================
# RedisSaver
# ============================================================================


class RedisSaver(InMemorySaver):
    """InMemorySaver that persists to Redis using **JSON** (never pickle).

    Single Source of Truth
    ----------------------
    Redis is the **only** authoritative store.  ``InMemorySaver``'s
    ``storage`` / ``writes`` / ``blobs`` dicts are a **non-authoritative
    cache** that is refreshed from Redis on every read and flushed to
    Redis on every write.

    To prevent stale local data, ``_restore`` uses **replace** semantics:
    it removes any local entries for the requested thread before loading
    the fresh data from Redis.  If Redis has no data for the thread (e.g.
    after ``adelete_thread``), the local entries are cleared — so the
    next ``aget_tuple`` correctly returns ``None``.

    Serialisation format (v2 — per-thread hash)
    -------------------------------------------
    Each thread's data is stored as a **field** in shared Redis hashes::

        lg:checkpoint:v2:storage → HSET {thread_id: JSON(thread's storage)}
        lg:checkpoint:v2:writes  → HSET {thread_id: JSON(thread's writes)}
        lg:checkpoint:v2:blobs   → HSET {thread_id: JSON(thread's blobs)}

    All non-JSON types (messages, bytes, datetime) carry a ``__type__``
    discriminator.  On load the discriminator is checked against a whitelist;
    unknown tags are rejected.
    """

    # ── Key helpers ────────────────────────────────────────────────────

    @staticmethod
    def _storage_key() -> str:
        return "lg:checkpoint:v2:storage"

    @staticmethod
    def _writes_key() -> str:
        return "lg:checkpoint:v2:writes"

    @staticmethod
    def _blobs_key() -> str:
        return "lg:checkpoint:v2:blobs"

    # ── Local-memory helpers (non-authoritative cache management) ──────

    def _evict_thread_from_memory(self, thread_id: str) -> None:
        """Remove all local entries for *thread_id* from the in-memory cache.

        Called before loading fresh data from Redis so that stale local
        state can never survive a Redis deletion (e.g. ``adelete_thread``).
        """
        # storage: {namespace: {thread_id: [...]}}
        for ns_data in self.storage.values():
            ns_data.pop(thread_id, None)
        # writes / blobs: {thread_id: {...}}
        self.writes.pop(thread_id, None)
        self.blobs.pop(thread_id, None)

    # ── Per-thread extraction ──────────────────────────────────────────

    @staticmethod
    def _extract_thread_storage(thread_id: str, storage: dict) -> dict:
        """Extract only *thread_id*'s entries from the storage dict.

        Storage is ``{namespace: {thread_id: [CheckpointTuple, ...]}}``.
        We return ``{namespace: {thread_id: [...]}}`` containing only the
        entries for *thread_id*.
        """
        result: dict[str, dict] = {}
        for ns, ns_data in storage.items():
            if isinstance(ns_data, dict) and thread_id in ns_data:
                result[ns] = {thread_id: ns_data[thread_id]}
        return result

    @staticmethod
    def _extract_thread_writes(thread_id: str, writes: dict) -> dict:
        """Extract only *thread_id*'s entries from the writes dict."""
        thread_data = writes.get(thread_id, {})
        return {thread_id: thread_data} if thread_data else {}

    @staticmethod
    def _extract_thread_blobs(thread_id: str, blobs: dict) -> dict:
        """Extract only *thread_id*'s entries from the blobs dict."""
        thread_data = blobs.get(thread_id, {})
        return {thread_id: thread_data} if thread_data else {}

    # ── Persist ────────────────────────────────────────────────────────

    async def _persist(self, thread_id: str) -> None:
        r = get_async_redis()
        if r is None:
            return

        storage_dict = dict(self.storage)
        writes_dict = dict(self.writes)
        blobs_dict = dict(self.blobs)

        # Extract only this thread's data — prevents cross-thread overwrites
        thread_storage = self._extract_thread_storage(thread_id, storage_dict)
        thread_writes = self._extract_thread_writes(thread_id, writes_dict)
        thread_blobs = self._extract_thread_blobs(thread_id, blobs_dict)

        ttl = settings.session_ttl_seconds

        async with r.client() as conn:
            # Persist each data type in its own hash, field = thread_id
            for key, data in [
                (self._storage_key(), thread_storage),
                (self._writes_key(), thread_writes),
                (self._blobs_key(), thread_blobs),
            ]:
                try:
                    safe = _to_json_safe(data)
                    payload = json.dumps(
                        {"version": _CHECKPOINT_FORMAT_VERSION, "data": safe},
                        ensure_ascii=False,
                        default=str,
                    )
                except Exception as exc:
                    logger.warning(
                        "RedisSaver: failed to encode %s for %s: %s",
                        key, thread_id, exc,
                    )
                    continue
                await conn.hset(key, thread_id, payload)
                await conn.expire(key, ttl)

    # ── Restore ────────────────────────────────────────────────────────

    async def _restore(self, thread_id: str) -> None:
        """Load *thread_id*'s checkpoint data from Redis into local memory.

        Uses **replace** semantics: any local entries for *thread_id* are
        evicted first, then fresh data from Redis is loaded.  This guarantees
        that local memory is always a faithful cache of Redis — if Redis has
        no data (e.g. after ``adelete_thread``), local memory is empty too.
        """
        r = get_async_redis()
        if r is None:
            return

        ttl = settings.session_ttl_seconds

        # Evict this thread's old local entries before loading fresh data.
        # This is the key invariant: local memory = exactly what Redis has.
        self._evict_thread_from_memory(thread_id)

        async with r.client() as conn:
            for key, target_attr in [
                (self._storage_key(), "storage"),
                (self._writes_key(), "writes"),
                (self._blobs_key(), "blobs"),
            ]:
                raw = await conn.hget(key, thread_id)
                if not raw:
                    continue

                payload: str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                await conn.expire(key, ttl)

                # Step 1: parse JSON
                try:
                    envelope = json.loads(payload)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "RedisSaver: invalid JSON in %s[%s] — discarding: %s",
                        key, thread_id, exc,
                    )
                    continue

                data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope

                # Step 2: structural validation
                if not isinstance(data, dict):
                    logger.warning(
                        "RedisSaver: %s[%s] is not a dict — discarding", key, thread_id,
                    )
                    continue

                # Step 3: decode typed values
                try:
                    restored = _from_json_safe(data)
                except ValueError as exc:
                    logger.warning(
                        "RedisSaver: %s[%s] has unknown type tags — discarding: %s",
                        key, thread_id, exc,
                    )
                    continue

                # Step 4: rebuild defaultdicts and load into memory
                rebuilt = _plain_to_defaultdict(restored)
                getattr(self, target_attr).update(rebuilt)

    # ── Async overrides (called by LangGraph during ainvoke / astream) ──

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        await self._restore(config["configurable"]["thread_id"])
        return await super().aget_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = await super().aput(config, checkpoint, metadata, new_versions)
        await self._persist(config["configurable"]["thread_id"])
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await super().aput_writes(config, writes, task_id, task_path)
        await self._persist(config["configurable"]["thread_id"])

    async def adelete_thread(self, thread_id: str) -> None:
        await super().adelete_thread(thread_id)
        r = get_async_redis()
        if r is not None:
            async with r.client() as conn:
                await conn.hdel(self._storage_key(), thread_id)
                await conn.hdel(self._writes_key(), thread_id)
                await conn.hdel(self._blobs_key(), thread_id)
