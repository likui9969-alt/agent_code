"""本地 JSON 对话历史存储 — 预留 Redis 接口。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class HistoryStore:
    """JSON-file backed chat history.

    Data stored in ``data/chat_history.json``.

    Schema::

        {
          "chats": [
            {
              "id": "uuid",
              "title": "用户输入前30字",
              "created_at": 1717920000.0,
              "updated_at": 1717920000.0,
              "messages": [...],
              "code": "...",
              "thread_id": "..."
            }
          ]
        }
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "chat_history.json"
        self._cache: dict[str, Any] = self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"chats": []}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── CRUD ────────────────────────────────────────────────────────────

    def list_chats(self, limit: int = 50) -> list[dict]:
        """Return recent chats, newest first."""
        chats = sorted(
            self._cache.get("chats", []),
            key=lambda c: c.get("updated_at", 0),
            reverse=True,
        )
        return chats[:limit]

    def get_chat(self, chat_id: str) -> dict | None:
        for c in self._cache.get("chats", []):
            if c["id"] == chat_id:
                return c
        return None

    def create_chat(self, title: str = "新建对话") -> str:
        import uuid
        chat = {
            "id": str(uuid.uuid4())[:8],
            "title": title[:40],
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": [],
            "code": "",
            "thread_id": "",
        }
        self._cache.setdefault("chats", []).append(chat)
        self._save()
        return chat["id"]

    def update_chat(self, chat_id: str, **kwargs: Any) -> bool:
        for c in self._cache.get("chats", []):
            if c["id"] == chat_id:
                c.update(kwargs)
                c["updated_at"] = time.time()
                self._save()
                return True
        return False

    def delete_chat(self, chat_id: str) -> bool:
        chats = self._cache.get("chats", [])
        new_list = [c for c in chats if c["id"] != chat_id]
        if len(new_list) != len(chats):
            self._cache["chats"] = new_list
            self._save()
            return True
        return False

    def rename_chat(self, chat_id: str, new_title: str) -> bool:
        return self.update_chat(chat_id, title=new_title[:40])

    def save_messages(self, chat_id: str, messages: list[dict]) -> bool:
        """Persist the message list for a chat."""
        return self.update_chat(chat_id, messages=messages)

    def save_code(self, chat_id: str, code: str) -> bool:
        return self.update_chat(chat_id, code=code)

    def save_thread(self, chat_id: str, thread_id: str) -> bool:
        return self.update_chat(chat_id, thread_id=thread_id)


# Module-level singleton
_history_store: HistoryStore | None = None


def get_history_store() -> HistoryStore:
    global _history_store
    if _history_store is None:
        _history_store = HistoryStore()
    return _history_store
