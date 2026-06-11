"""API client for the AI Code Assistant backend.

Call flow
---------

    Streamlit                    FastAPI
    ─────────                    ───────
    post_chat(input)  ────────►  POST /chat
         │                       │
         │  ←── SSE events ──    │  planner → code → tools → review → human
         │                       │
    [if paused: show buttons]    │
    post_resume(id, approved) ─► POST /chat/{id}/resume
         │                       │
         │  ←── SSE events ──    │  human → END
         ▼                       ▼
    display final code
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx


def _iter_sse_events(lines) -> Iterator[dict]:
    """Parse SSE ``event:`` + ``data:`` pairs (mirrors test_stream.parse_sse)."""
    current: dict[str, Any] = {}
    for line in lines:
        if not line:
            if current:
                yield current
                current = {}
            continue
        if line.startswith("event: "):
            current["_event"] = line[7:]
        elif line.startswith("data: "):
            current.update(json.loads(line[6:]))
    if current:
        yield current


class APIClient:
    """Thin HTTP wrapper around the backend API."""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=120.0)

    # ── Core endpoints ──────────────────────────────────────────────────

    def post_chat(
        self,
        user_input: str,
        thread_id: str | None = None,
        project_path: str | None = None,
    ) -> dict:
        """POST /chat — start agent pipeline.  Returns parsed JSON response."""
        body: dict[str, Any] = {"input": user_input}
        if thread_id:
            body["thread_id"] = thread_id
        if project_path:
            body["project_path"] = project_path
        r = self._client.post(f"{self.base_url}/chat", json=body)
        r.raise_for_status()
        return r.json()

    def post_chat_stream(
        self,
        user_input: str,
        thread_id: str | None = None,
        project_path: str | None = None,
    ) -> Iterator[dict]:
        """POST /chat/stream — SSE streaming.  Yields parsed event dicts."""
        body: dict[str, Any] = {"input": user_input}
        if thread_id:
            body["thread_id"] = thread_id
        if project_path:
            body["project_path"] = project_path
        with self._client.stream("POST", f"{self.base_url}/chat/stream", json=body) as r:
            r.raise_for_status()
            yield from _iter_sse_events(r.iter_lines())

    def post_resume(
        self,
        thread_id: str,
        action: str,
        feedback: str = "",
        project_path: str | None = None,
    ) -> dict:
        """POST /chat/{id}/resume — human decision."""
        body: dict[str, Any] = {"action": action, "feedback": feedback}
        if project_path:
            body["project_path"] = project_path
        r = self._client.post(
            f"{self.base_url}/chat/{thread_id}/resume",
            json=body,
        )
        r.raise_for_status()
        return r.json()

    def post_resume_stream(
        self,
        thread_id: str,
        action: str,
        feedback: str = "",
        project_path: str | None = None,
    ) -> Iterator[dict]:
        """POST /chat/{id}/resume/stream — resume + SSE stream."""
        body: dict[str, Any] = {"action": action, "feedback": feedback}
        if project_path:
            body["project_path"] = project_path
        with self._client.stream(
            "POST",
            f"{self.base_url}/chat/{thread_id}/resume/stream",
            json=body,
        ) as r:
            r.raise_for_status()
            yield from _iter_sse_events(r.iter_lines())

    def get_state(self, thread_id: str) -> dict:
        """GET /chat/{id}/state."""
        r = self._client.get(f"{self.base_url}/chat/{thread_id}/state")
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        """GET /health."""
        return self._client.get(f"{self.base_url}/health").json()

    def list_tools(self) -> dict:
        """GET /tools."""
        return self._client.get(f"{self.base_url}/tools").json()

    def configure_llm(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> dict:
        """POST /settings/llm — push API key / model to the backend."""
        body: dict[str, Any] = {}
        if api_key is not None:
            body["api_key"] = api_key
        if model is not None:
            body["model"] = model
        r = self._client.post(f"{self.base_url}/settings/llm", json=body)
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()
