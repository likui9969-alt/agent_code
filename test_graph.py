"""Smoke test for graph — Graph + Tools + Memory + HITL.

Uses ``unittest.mock`` to patch LLM calls so tests run without a real API key.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("QWEN_API_KEY", "")  # Ensure no real key leaks in

PROJECT_ROOT = str(Path(__file__).resolve().parent)

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.graph import build_graph
from app.project_workspace import project_root_context
from app.tools.registry import tool_registry


# ── Mock LLM responses ─────────────────────────────────────────────────────
# Each key = "role|hint" — the side_effect callback matches on hint substrings.

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
    """Fake LLM — returns appropriate mock responses based on input content."""
    combined = (system + user).lower()

    # Planner
    if "senior software architect" in system:
        if "sort" in user.lower() or "quicksort" in user.lower():
            return _MOCK_PLANNER_SORT
        if "api" in user.lower() or "fastapi" in user.lower():
            return _MOCK_PLANNER_API
        return "## Plan\n1. Do stuff."

    # Reviewer
    if "code reviewer" in system:
        if "fastapi" in combined or "crud" in combined:
            # First call → fail, second → pass  (call count tracked via side_effect)
            return _MOCK_REVIEW_FAIL
        return _MOCK_REVIEW_PASS

    # Coder
    if "fix" in system.lower() or "issues to fix" in user.lower():
        # Auto-fix path → return v2 (full CRUD)
        return _MOCK_CODE_API_V2
    if "sort" in user.lower() or "quicksort" in user.lower():
        return _MOCK_CODE_SORT
    if "api" in user.lower() or "fastapi" in user.lower():
        return _MOCK_CODE_API_V1

    return "```python\ndef solution():\n    pass\n```"


def _base_state(user_input: str, tid: str) -> dict:
    return {
        "session_id": tid,
        "input": user_input,
        "plan": "",
        "code": "",
        "review": {"passed": False, "issues": []},
        "iteration_count": 0,
        "human_feedback": "",
        "approval_status": "pending",
        "error": "",
        "tool_calls": [],
        "tool_results": [],
        "messages": [HumanMessage(content=user_input)],
        "project_root": PROJECT_ROOT,
        "target_file": "output.py",
    }


async def main() -> None:
    graph = build_graph()

    # ════════════════════════════════════════════════════════════════════
    # Test 1 — quicksort: tools + review → human → approve
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 1: quicksort — tools: write_file → run_python → review")
    print("=" * 60)

    tid = "test-tools-1"
    initial = _base_state("Write a quicksort function", tid)

    with patch("app.agents.chat", side_effect=_mock_chat):
        with project_root_context(PROJECT_ROOT):
            result = await graph.ainvoke(initial, {"configurable": {"thread_id": tid}})

    snap = await graph.aget_state({"configurable": {"thread_id": tid}})
    if snap and snap.interrupts:
        print("  [PAUSED] at human_approval after tools+review")
        with patch("app.agents.chat", side_effect=_mock_chat):
            with project_root_context(PROJECT_ROOT):
                result = await graph.ainvoke(
                    Command(resume={"action": "approved", "feedback": "Good"}),
                    {"configurable": {"thread_id": tid}},
                )

    tc = result.get("tool_calls", [])
    tr = result.get("tool_results", [])
    print(f"  tool_calls  : {len(tc)} entries")
    for t in tc:
        print(f"    - {t['tool_name']}: {t['status']}")
    print(f"  tool_results: {len(tr)} results")
    for r in tr:
        print(f"    - {r['tool_name']}: success={r['success']}")

    assert len(tr) >= 2, f"Expected >=2 tool results, got {len(tr)}"
    assert any(r["tool_name"] == "write_file" and r["success"] for r in tr), "write_file failed"
    # run_python now returns success=False (backend not implemented)
    assert any(r["tool_name"] == "run_python" for r in tr), "run_python not called"
    print("  [PASSED]\n")

    # ════════════════════════════════════════════════════════════════════
    # Test 2 — tool registry standalone
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 2: ToolRegistry standalone")
    print("=" * 60)

    tools = tool_registry.list_tools()
    schemas = tool_registry.get_all_schemas()
    print(f"  registered : {tools}")
    print(f"  schemas    : {len(schemas)} tools")

    with project_root_context(PROJECT_ROOT):
        r = tool_registry.execute("read_file", {"path": "README.md"}, project_root=PROJECT_ROOT)
        print(f"  read_file  : success={r.success}, lines={r.metadata.get('total_lines')}")
        assert r.success

        r = tool_registry.execute("grep", {"pattern": "LangGraph"}, project_root=PROJECT_ROOT)
        print(f"  grep       : success={r.success}, matches={r.metadata.get('total_matches')}")
        assert r.success

        r = tool_registry.execute("list_files", {"glob": "*.py"}, project_root=PROJECT_ROOT)
        print(f"  list_files : success={r.success}, count={r.metadata.get('file_count')}")
        assert r.success

        # run_python: now returns success=False with "not implemented" error
        r = tool_registry.execute("run_python", {"code": "print('hello')"}, project_root=PROJECT_ROOT)
        print(f"  run_python : success={r.success}, error={r.error[:60]}")
        assert not r.success
        assert "not implemented" in r.error.lower()

        r = tool_registry.execute("nonexistent", {}, project_root=PROJECT_ROOT)
    print(f"  bad_tool   : success={r.success}, error={r.error[:50]}...")
    assert not r.success

    print("  [PASSED]\n")

    # ════════════════════════════════════════════════════════════════════
    # Test 3 — tool execution log
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 3: Execution log audit trail")
    print("=" * 60)

    log = tool_registry.get_execution_log()
    print(f"  total entries : {len(log)}")
    for entry in log[:5]:
        print(f"    [{entry['tool_name']}] {entry['id']} | "
              f"{'OK' if entry['result']['success'] else 'FAIL'} | "
              f"{entry['duration_ms']:.1f}ms")
    assert len(log) >= 5, f"Expected >=5 log entries, got {len(log)}"
    print("  [PASSED]\n")

    # ════════════════════════════════════════════════════════════════════
    # Test 4 — API CRUD: auto-fix loop → human → done
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 4: API CRUD — tools → auto-fix → tools → human → done")
    print("=" * 60)

    # reviewer returns fail first, pass second — use side_effect with list
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

    tid4 = "test-tools-api"
    with patch("app.agents.chat", side_effect=_mock_chat_api):
        with project_root_context(PROJECT_ROOT):
            result = await graph.ainvoke(
                _base_state("Build a FastAPI CRUD microservice", tid4),
                {"configurable": {"thread_id": tid4}},
            )

    snap = await graph.aget_state({"configurable": {"thread_id": tid4}})
    if snap and snap.interrupts:
        print("  [PAUSED] after auto-review+tool loop")
        with patch("app.agents.chat", side_effect=_mock_chat_api):
            with project_root_context(PROJECT_ROOT):
                result = await graph.ainvoke(
                    Command(resume={"action": "approved", "feedback": ""}),
                    {"configurable": {"thread_id": tid4}},
                )

    tc = result.get("tool_calls", [])
    tr = result.get("tool_results", [])
    print(f"  tool calls   : {len(tc)}")
    print(f"  tool results : {len(tr)}")
    print(f"  iter_count   : {result.get('iteration_count')}")
    print(f"  has write    : {any(r['tool_name'] == 'write_file' for r in tr)}")
    print(f"  has run      : {any(r['tool_name'] == 'run_python' for r in tr)}")
    print(f"  code OK      : {'@app.patch' in result.get('code', '')}")
    assert len(tr) >= 2
    print("  [PASSED]\n")

    print("All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
