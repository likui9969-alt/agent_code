"""Smoke test — verify SSE streaming output.

Tests /chat/stream and /chat/{id}/resume/stream (human-in-the-loop).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

os.environ.setdefault("REDIS_ENABLED", "false")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
    with client.stream(
        "POST", "/chat/stream",
        json={"input": "Write a quicksort function", "thread_id": tid},
        headers={"Content-Type": "application/json"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        events = parse_sse(resp)

    event_types = [e.pop("_event", "?") for e in events]
    print(f"  Events: {len(events)} — {event_types}")

    # Assert event sequence
    assert event_types[0] == "start"
    assert "node_start" in event_types
    assert "node_done" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "interrupt"  # pauses at human_approval

    # Verify node flow
    nodes = [e["node"] for e in events if e.get("node")]
    print(f"  Nodes executed: {nodes}")
    assert "planner" in nodes
    assert "code_agent" in nodes
    assert "tool_node" in nodes
    assert "reviewer" in nodes

    # Verify tool events
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

    # Step 1: initial stream
    with client.stream(
        "POST", "/chat/stream",
        json={"input": "Write a quicksort function", "thread_id": tid},
        headers={"Content-Type": "application/json"},
    ) as resp:
        events1 = parse_sse(resp)

    assert events1[-1]["_event"] == "interrupt"
    print(f"  Step 1: {len(events1)} events, ends with interrupt")

    # Step 2: resume stream
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

    tid = f"stream-{uuid.uuid4().hex[:6]}"
    with client.stream(
        "POST", "/chat/stream",
        json={"input": "Build a FastAPI CRUD microservice", "thread_id": tid},
        headers={"Content-Type": "application/json"},
    ) as resp:
        events = parse_sse(resp)

    event_types = [e.pop("_event", "?") for e in events]
    nodes = [e["node"] for e in events if e.get("node")]
    print(f"  Events: {len(events)}")
    print(f"  Nodes:  {nodes}")

    # Should see code_agent → tool_node → code_agent → tool_node → reviewer cycle
    assert nodes.count("code_agent") >= 2  # first gen + auto-fix
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

    # 404 — nonexistent thread
    resp = client.post(
        "/chat/nonexistent/resume/stream",
        json={"action": "approved", "feedback": ""},
    )
    assert resp.status_code >= 400, f"Expected error status, got {resp.status_code}"
    print(f"  nonexistent thread → {resp.status_code}: OK")

    # 400 — thread exists but not paused (it completed)
    tid = f"stream-{uuid.uuid4().hex[:6]}"
    # First complete a run
    client.post("/chat", json={"input": "Write a quicksort function", "thread_id": tid})
    client.post(f"/chat/{tid}/resume", json={"action": "approved", "feedback": ""})
    # Now try to resume stream on completed thread
    resp = client.post(
        f"/chat/{tid}/resume/stream",
        json={"action": "approved", "feedback": ""},
    )
    assert resp.status_code == 400
    print("  completed thread → 400: OK")

    print("  [PASSED]\n")
    print("All streaming tests passed!")


if __name__ == "__main__":
    test_stream_basic()
    test_stream_resume()
    test_stream_api_with_loop()
    test_stream_validation()
