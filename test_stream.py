"""Smoke test — verify SSE streaming output.

Tests /chat/stream and /chat/{id}/resume/stream (human-in-the-loop).
Uses ``unittest.mock`` to patch LLM calls so tests run without a real API key.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("QWEN_API_KEY", "")

PROJECT_ROOT = str(Path(__file__).resolve().parent)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── Mock LLM responses ─────────────────────────────────────────────────────

_MOCK_PLANNER_SORT = (
    "## Implementation Plan\n\n"
    "**Task**: Write a quicksort function\n\n"
    "1. **Algorithm**: QuickSort — O(n log n) average.\n"
    "2. **Signature**: ``def quicksort(arr: list) -> list``.\n"
    "3. **Logic**: base-case → pivot → partition → recurse.\n"
    "4. **Edge cases**: empty, single, duplicates, already-sorted.\n"
    "5. **Test**: 5 cases in ``__main__``."
)

_MOCK_CODE_SORT = (
    "```python\n"
    "def quicksort(arr: list) -> list:\n"
    '    """Sort a list using QuickSort."""\n'
    "    if len(arr) <= 1:\n        return arr\n"
    "    pivot = arr[len(arr) // 2]\n"
    "    left  = [x for x in arr if x < pivot]\n"
    "    mid   = [x for x in arr if x == pivot]\n"
    "    right = [x for x in arr if x > pivot]\n"
    "    return quicksort(left) + mid + quicksort(right)\n\n\n"
    'if __name__ == "__main__":\n'
    '    print(quicksort([3,1,2]))\n'
    "```"
)

_MOCK_PLANNER_API = (
    "## Implementation Plan\n\n"
    "**Task**: Build a FastAPI CRUD microservice\n\n"
    "1. **Framework**: FastAPI + Pydantic v2.\n"
    "2. **Routes**: full CRUD — GET /, POST/GET/PATCH/DELETE /items.\n"
    "3. **Model**: Item with name, price (>0), optional description.\n"
    "4. **Error handling**: HTTPException 400/404, rate-limit middleware.\n"
    "5. **Run**: ``uvicorn main:app --reload``."
)

_MOCK_CODE_API_V1 = (
    "```python\n"
    "from fastapi import FastAPI, HTTPException\n"
    "from pydantic import BaseModel, Field\n\n\n"
    "app = FastAPI(title=\"Sample API\", version=\"1.0.0\")\n\n\n"
    "class Item(BaseModel):\n"
    '    name: str = Field(..., min_length=1)\n'
    '    price: float = Field(..., gt=0)\n'
    "    description: str | None = None\n\n\n"
    '@app.get("/")\n'
    "async def root() -> dict:\n"
    '    return {"message": "Hello from Sample API"}\n\n\n'
    '@app.post("/items/", status_code=201)\n'
    "async def create_item(item: Item) -> dict:\n"
    '    return {"item": item.model_dump()}\n\n\n'
    '@app.get("/items/{item_id}")\n'
    "async def get_item(item_id: int) -> dict:\n"
    "    if item_id < 0:\n"
    '        raise HTTPException(400, "Item ID must be >= 0")\n'
    '    return {"item_id": item_id}\n'
    "```"
)

_MOCK_CODE_API_V2 = (
    "```python\n"
    "from fastapi import FastAPI, HTTPException, Request\n"
    "from pydantic import BaseModel, Field\nimport time\n\n\n"
    'app = FastAPI(title="Sample API", version="2.0.0")\n\n\n'
    "# ── Rate limiter ──\n"
    "_rate_store: dict[str, list[float]] = {}\n"
    "RATE_WINDOW = 60\nRATE_LIMIT  = 100\n\n\n"
    '@app.middleware("http")\n'
    "async def rate_limit_middleware(request: Request, call_next):\n"
    "    ip = request.client.host\nnow = time.time()\n"
    "    _rate_store.setdefault(ip, [])\n"
    '    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]\n'
    "    if len(_rate_store[ip]) >= RATE_LIMIT:\n"
    '        raise HTTPException(429, "Too Many Requests")\n'
    "    _rate_store[ip].append(now)\n"
    "    return await call_next(request)\n\n\n"
    "class Item(BaseModel):\n"
    '    name: str = Field(..., min_length=1)\n'
    '    price: float = Field(..., gt=0)\n'
    "    description: str | None = None\n\n\n"
    "class ItemUpdate(BaseModel):\n"
    "    name: str | None = None\n"
    "    price: float | None = None\n"
    "    description: str | None = None\n\n\n"
    '@app.get("/")\n'
    "async def root() -> dict:\n"
    '    return {"message": "Hello from Sample API v2"}\n\n\n'
    '@app.post("/items/", status_code=201)\n'
    "async def create_item(item: Item) -> dict:\n"
    '    return {"item": item.model_dump(), "status": "created"}\n\n\n'
    '@app.get("/items/{item_id}")\n'
    "async def get_item(item_id: int) -> dict:\n"
    "    if item_id < 0:\n"
    '        raise HTTPException(400, "Item ID must be >= 0")\n'
    '    return {"item_id": item_id, "name": f"Item-{item_id}"}\n\n\n'
    '@app.patch("/items/{item_id}")\n'
    "async def update_item(item_id: int, update: ItemUpdate) -> dict:\n"
    "    if item_id < 0:\n"
    '        raise HTTPException(400, "Item ID must be >= 0")\n'
    '    return {"item_id": item_id, "update": update.model_dump(exclude_none=True)}\n\n\n'
    '@app.delete("/items/{item_id}")\n'
    "async def delete_item(item_id: int) -> dict:\n"
    "    if item_id < 0:\n"
    '        raise HTTPException(400, "Item ID must be >= 0")\n'
    '    return {"item_id": item_id, "status": "deleted"}\n'
    "```"
)

_MOCK_REVIEW_PASS = '{"passed": true, "issues": []}'
_MOCK_REVIEW_FAIL = (
    '{"passed": false, "issues": ['
    '"Missing PATCH /items/{item_id} endpoint", '
    '"Missing DELETE /items/{item_id} endpoint", '
    '"No rate-limiting middleware"'
    ']}'
)


def _mock_chat(system: str, user: str, **kwargs) -> str:
    """Fake LLM returning canned responses based on input content."""
    combined = (system + user).lower()

    if "senior software architect" in system:
        if "sort" in user.lower() or "quicksort" in user.lower():
            return _MOCK_PLANNER_SORT
        if "api" in user.lower() or "fastapi" in user.lower():
            return _MOCK_PLANNER_API
        return "## Plan\n1. Do stuff."

    if "code reviewer" in system:
        if "fastapi" in combined or "crud" in combined:
            return _MOCK_REVIEW_FAIL
        return _MOCK_REVIEW_PASS

    if "fix" in system.lower() or "issues to fix" in user.lower():
        return _MOCK_CODE_API_V2
    if "sort" in user.lower() or "quicksort" in user.lower():
        return _MOCK_CODE_SORT
    if "api" in user.lower() or "fastapi" in user.lower():
        return _MOCK_CODE_API_V1

    return "```python\ndef solution():\n    pass\n```"


def parse_sse(response) -> list[dict]:
    """Parse SSE text/event-stream into a list of event dicts."""
    events = []
    current = {}
    for line in response.iter_lines():
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["_event"] = line[7:]
        elif line.startswith("data: "):
            current.update(json.loads(line[6:]))
    if current:
        events.append(current)
    return events


def test_stream_basic():
    """Quicksort: full stream → interrupt → no error."""
    print("=" * 60)
    print("Test 1: POST /chat/stream — quicksort (expect start..interrupt)")
    print("=" * 60)

    tid = f"stream-{uuid.uuid4().hex[:6]}"
    with patch("app.agents.chat", side_effect=_mock_chat):
        with client.stream(
            "POST", "/chat/stream",
            json={"input": "Write a quicksort function", "thread_id": tid, "project_path": PROJECT_ROOT},
            headers={"Content-Type": "application/json"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
            events = parse_sse(resp)

    event_types = [e.pop("_event", "?") for e in events]
    print(f"  Events: {len(events)} — {event_types}")

    assert event_types[0] == "start"
    assert "node_start" in event_types
    assert "node_done" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "interrupt"

    nodes = [e["node"] for e in events if e.get("node")]
    print(f"  Nodes executed: {nodes}")
    assert "planner" in nodes
    assert "code_agent" in nodes
    assert "tool_node" in nodes
    assert "reviewer" in nodes

    tool_calls = [e for e in events if e.get("tool_name") and e.get("arguments")]
    tool_results = [e for e in events if e.get("tool_name") and e.get("success") is not None]
    print(f"  Tool calls: {len(tool_calls)}, Tool results: {len(tool_results)}")
    assert len(tool_calls) >= 1
    assert len(tool_results) >= 1

    print("  [PASSED]\n")
    return tid


def test_stream_resume():
    """Full cycle: stream → interrupt → resume stream → done."""
    print("=" * 60)
    print("Test 2: POST /chat/stream → interrupt → /resume/stream → done")
    print("=" * 60)

    tid = f"stream-{uuid.uuid4().hex[:6]}"

    with patch("app.agents.chat", side_effect=_mock_chat):
        with client.stream(
            "POST", "/chat/stream",
            json={"input": "Write a quicksort function", "thread_id": tid, "project_path": PROJECT_ROOT},
            headers={"Content-Type": "application/json"},
        ) as resp:
            events1 = parse_sse(resp)

    assert events1[-1]["_event"] == "interrupt"
    print(f"  Step 1: {len(events1)} events, ends with interrupt")

    with patch("app.agents.chat", side_effect=_mock_chat):
        with client.stream(
            "POST", f"/chat/{tid}/resume/stream",
            json={"action": "approved", "feedback": "LGTM"},
            headers={"Content-Type": "application/json"},
        ) as resp:
            assert resp.status_code == 200
            events2 = parse_sse(resp)

    event_types2 = [e.pop("_event", "?") for e in events2]
    print(f"  Step 2: {len(events2)} events — {event_types2}")

    assert event_types2[0] == "resume"
    assert event_types2[-1] == "done"

    print("  [PASSED]\n")


def test_stream_api_with_loop():
    """API CRUD: stream → auto-fix loop → interrupt (pauses for human)."""
    print("=" * 60)
    print("Test 3: API CRUD stream — auto-fix loop visible in events")
    print("=" * 60)

    review_responses = [_MOCK_REVIEW_FAIL, _MOCK_REVIEW_PASS, _MOCK_REVIEW_PASS]

    def _mock_chat_api(system: str, user: str, **kwargs) -> str:
        combined = (system + user).lower()
        if "senior software architect" in system:
            return _MOCK_PLANNER_API
        if "code reviewer" in system:
            resp = review_responses.pop(0) if review_responses else _MOCK_REVIEW_PASS
            return resp
        if "fix" in system.lower() or "issues to fix" in user.lower():
            return _MOCK_CODE_API_V2
        return _MOCK_CODE_API_V1

    tid = f"stream-{uuid.uuid4().hex[:6]}"
    with patch("app.agents.chat", side_effect=_mock_chat_api):
        with client.stream(
            "POST", "/chat/stream",
            json={"input": "Build a FastAPI CRUD microservice", "thread_id": tid, "project_path": PROJECT_ROOT},
            headers={"Content-Type": "application/json"},
        ) as resp:
            events = parse_sse(resp)

    event_types = [e.pop("_event", "?") for e in events]
    nodes = [e["node"] for e in events if e.get("node")]
    print(f"  Events: {len(events)}")
    print(f"  Nodes:  {nodes}")

    assert nodes.count("code_agent") >= 2
    assert nodes.count("tool_node") >= 2
    assert nodes.count("reviewer") >= 1
    assert "planner" in nodes
    assert event_types[-1] == "interrupt"

    print("  [PASSED]\n")


def test_stream_validation():
    """Error cases: missing thread, not paused."""
    print("=" * 60)
    print("Test 4: Error handling")
    print("=" * 60)

    resp = client.post(
        "/chat/nonexistent/resume/stream",
        json={"action": "approved", "feedback": ""},
    )
    assert resp.status_code >= 400, f"Expected error status, got {resp.status_code}"
    print(f"  nonexistent thread -> {resp.status_code}: OK")

    tid = f"stream-{uuid.uuid4().hex[:6]}"
    with patch("app.agents.chat", side_effect=_mock_chat):
        client.post("/chat", json={"input": "Write a quicksort function", "thread_id": tid, "project_path": PROJECT_ROOT})
        client.post(f"/chat/{tid}/resume", json={"action": "approved", "feedback": ""})
    resp = client.post(
        f"/chat/{tid}/resume/stream",
        json={"action": "approved", "feedback": ""},
    )
    assert resp.status_code == 400
    print("  completed thread -> 400: OK")

    print("  [PASSED]\n")
    print("All streaming tests passed!")


if __name__ == "__main__":
    test_stream_basic()
    test_stream_resume()
    test_stream_api_with_loop()
    test_stream_validation()
