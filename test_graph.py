"""Smoke test for v4 — Graph + Tools + Memory + HITL."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("REDIS_ENABLED", "false")

PROJECT_ROOT = str(Path(__file__).resolve().parent)

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.graph import build_graph
from app.project_workspace import project_root_context
from app.tools.registry import tool_registry


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
        "tool_calls": [],
        "tool_results": [],
        "messages": [HumanMessage(content=user_input)],
        "project_root": PROJECT_ROOT,
        "target_file": "output.py",
    }


async def main() -> None:
    graph = build_graph()

    # ════════════════════════════════════════════════════════════════════
    # Test 1 — tools execute: write_file → run_python → reviewer
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 1: quicksort — tools: write_file → run_python → review")
    print("=" * 60)

    tid = "test-tools-1"
    initial = _base_state("Write a quicksort function", tid)

    with project_root_context(PROJECT_ROOT):
        result = await graph.ainvoke(initial, {"configurable": {"thread_id": tid}})

    # Should pause at human_approval (after code_agent→tools→reviewer)
    snap = await graph.aget_state({"configurable": {"thread_id": tid}})
    if snap and snap.interrupts:
        print(f"  [PAUSED] at human_approval after tools+review")
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

    assert len(tr) >= 2, f"Expected ≥2 tool results, got {len(tr)}"
    assert any(r["tool_name"] == "write_file" and r["success"] for r in tr), "write_file failed"
    assert any(r["tool_name"] == "run_python" and r["success"] for r in tr), "run_python failed"
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
        # Test read_file
        r = tool_registry.execute("read_file", {"path": "README.md"}, project_root=PROJECT_ROOT)
        print(f"  read_file  : success={r.success}, lines={r.metadata.get('total_lines')}")
        assert r.success

        # Test grep
        r = tool_registry.execute("grep", {"pattern": "LangGraph"}, project_root=PROJECT_ROOT)
        print(f"  grep       : success={r.success}, matches={r.metadata.get('total_matches')}")
        assert r.success

        # Test list_files
        r = tool_registry.execute("list_files", {"glob": "*.py"}, project_root=PROJECT_ROOT)
        print(f"  list_files : success={r.success}, count={r.metadata.get('file_count')}")
        assert r.success

        # Test run_python (inline)
        r = tool_registry.execute("run_python", {"code": "print('hello from sandbox')"}, project_root=PROJECT_ROOT)
        print(f"  run_python : success={r.success}, output={r.output[:60]}")
        assert r.success

        # Test invalid tool
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
    assert len(log) >= 5, f"Expected ≥5 log entries, got {len(log)}"
    print("  [PASSED]\n")

    # ════════════════════════════════════════════════════════════════════
    # Test 4 — full flow with tools (API CRUD)
    # ════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("Test 4: API CRUD — tools → auto-fix → tools → human → done")
    print("=" * 60)

    tid4 = "test-tools-api"
    with project_root_context(PROJECT_ROOT):
        result = await graph.ainvoke(
            _base_state("Build a FastAPI CRUD microservice", tid4),
            {"configurable": {"thread_id": tid4}},
        )

    snap = await graph.aget_state({"configurable": {"thread_id": tid4}})
    if snap and snap.interrupts:
        print(f"  [PAUSED] after auto-review+tool loop")
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
