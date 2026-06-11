"""SSE streaming layer for LangGraph agent execution.

Architecture
------------
::

    POST /chat/stream
        │
        ▼
    async generator ──► graph.astream(stream_mode="updates")
        │                      │
        │               {node: partial_state}
        │                      │
        ▼                      ▼
    SSE frame           _format_event()
    (text/event-stream)
        │
        ▼
    Client (curl / browser EventSource)

Human-in-the-Loop
-----------------
When the graph hits ``human_approval``, the stream ends with an
``interrupt`` event.  The client then calls::

    POST /chat/{id}/resume/stream  {"action": "approved", ...}

which starts a **new** SSE stream continuing from the interrupt point.

Event reference
---------------
============= ======================================================
event          payload
============= ======================================================
``start``      ``{thread_id}``
``node_start`` ``{node, timestamp}``  (emitted before each node)
``node_done``  ``{node, output, duration_ms}``
``tool_call``  ``{tool_name, arguments}``
``tool_result`` ``{tool_name, result}``
``interrupt``  ``{thread_id, data}``   (graph paused)
``resume``     ``{action}``            (graph resumed)
``done``       ``{thread_id, summary}``
``error``      ``{message}``
============= ======================================================
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from app.state import AgentState
from app.schemas import ResumeRequest


# ============================================================================
# SSE wire format
# ============================================================================


def format_sse(event: str, data: dict | None = None) -> str:
    """Format a single SSE message frame.

    Returns:
        ``"event: {event}\\ndata: {json}\\n\\n"``
    """
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ============================================================================
# Node output sanitisation (strip verbose internals for the client)
# ============================================================================


def _sanitize(node_name: str, update: dict) -> dict[str, Any]:
    """Return a client-safe version of the node's state update.

    - ``messages`` are truncated to the **last** entry only (the client
      already receives structured events; full history is on ``/state``).
    - ``code`` is truncated to 2000 chars for the event; full code is on
      ``/state``.
    """
    clean: dict[str, Any] = {}
    for key, value in update.items():
        if key == "messages":
            # Only send the newest message
            if isinstance(value, list) and value:
                last = value[-1]
                clean["message"] = {
                    "role": type(last).__name__.replace("Message", "").lower(),
                    "content": str(last.content)[:500],
                }
        elif key == "code":
            clean[key] = str(value)[:2000]
        elif key == "tool_calls":
            clean[key] = [
                {
                    "id": tc.get("id"),
                    "tool_name": tc.get("tool_name"),
                    "arguments": tc.get("arguments"),
                    "status": tc.get("status"),
                }
                for tc in (value or [])
            ]
        elif key == "tool_results":
            clean[key] = [
                {
                    "tool_name": r.get("tool_name"),
                    "success": r.get("success"),
                    "output": str(r.get("output", ""))[:300],
                    "arguments": r.get("arguments", {}),
                    "metadata": r.get("metadata", {}),
                }
                for r in (value or [])
            ]
        elif key == "review":
            clean[key] = {
                "passed": value.get("passed"),
                "issues": value.get("issues", []),
            }
        elif key == "plan":
            clean[key] = str(value)[:1000]
        elif key == "approval_status":
            clean[key] = value
        elif key == "human_feedback":
            clean[key] = str(value)[:500]
        elif key == "iteration_count":
            clean[key] = value
        elif key in ("target_file", "project_root"):
            clean[key] = value
        else:
            # Skip internal fields
            pass
    return clean


# ============================================================================
# Async generators (consumed by StreamingResponse)
# ============================================================================


async def stream_chat(
    graph,
    initial_state: dict,
    config: dict,
    thread_id: str,
    project_path: str | None = None,
) -> AsyncIterator[str]:
    """Run the full graph and yield SSE events for every node.

    Yields:
        ``start``, ``node_start``, ``node_done``, ``tool_call``,
        ``tool_result``, ``interrupt``, ``done``, ``error``.
    """
    from app.project_workspace import set_project_root

    t_start = time.time()
    set_project_root(project_path or initial_state.get("project_root") or None)

    # ── Start ──
    yield format_sse("start", {"thread_id": thread_id})
    yield format_sse("node_start", {"node": "pipeline", "timestamp": time.time()})

    try:
        async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                t0 = time.time()

                # ── __interrupt__ is a pseudo-node emitted when the graph pauses.
                #     Its payload is a tuple of Interrupt objects, not a state dict.
                if node_name == "__interrupt__":
                    yield format_sse("node_done", {
                        "node": "human_approval",
                        "output": {"status": "paused"},
                        "duration_ms": 0,
                    })
                    continue

                # ── Before node ──
                yield format_sse("node_start", {
                    "node": node_name,
                    "timestamp": t0,
                })

                # ── Emit tool_call events for pending calls ──
                if node_name == "code_agent" and update.get("tool_calls"):
                    for tc in update["tool_calls"]:
                        if tc.get("status") == "pending":
                            yield format_sse("tool_call", {
                                "id": tc.get("id"),
                                "tool_name": tc.get("tool_name"),
                                "arguments": tc.get("arguments"),
                            })

                # ── Emit tool_result events ──
                if node_name == "tool_node" and update.get("tool_results"):
                    for r in update["tool_results"]:
                        yield format_sse("tool_result", {
                            "tool_name": r.get("tool_name"),
                            "success": r.get("success"),
                            "output": str(r.get("output", ""))[:300],
                        })

                # ── Node done ──
                duration = (time.time() - t0) * 1000
                yield format_sse("node_done", {
                    "node": node_name,
                    "output": _sanitize(node_name, update),
                    "duration_ms": round(duration, 1),
                })

    except Exception as exc:
        # LangGraph raises GraphInterrupt when interrupt() is called inside a node.
        # This is NOT an error — it's the expected Human-in-the-Loop pause.
        if "GraphInterrupt" in type(exc).__name__ or "interrupt" in str(exc).lower():
            pass  # fall through to interrupt check below
        else:
            yield format_sse("error", {"message": str(exc)})
            return

    # ── Check for interrupt ──
    snap = await graph.aget_state(config)
    if snap and snap.interrupts:
        interrupt_data = snap.interrupts[0].value if snap.interrupts else {}
        yield format_sse("interrupt", {
            "thread_id": thread_id,
            "actions": interrupt_data.get("actions", []),
            "message": interrupt_data.get("message", ""),
        })
    else:
        # ── Done ──
        total_ms = (time.time() - t_start) * 1000
        yield format_sse("done", {
            "thread_id": thread_id,
            "duration_ms": round(total_ms, 1),
        })


async def stream_resume(
    graph,
    config: dict,
    thread_id: str,
    resume_body: ResumeRequest,
    project_path: str | None = None,
) -> AsyncIterator[str]:
    """Resume a paused graph and stream the remaining node executions.

    This is a **new** SSE stream that continues from the interrupt point.
    """
    from langgraph.types import Command
    from app.project_workspace import set_project_root

    set_project_root(project_path or None)

    yield format_sse("resume", {
        "thread_id": thread_id,
        "action": resume_body.action,
    })

    cmd = Command(resume={"action": resume_body.action, "feedback": resume_body.feedback})

    try:
        async for chunk in graph.astream(cmd, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                t0 = time.time()

                if node_name == "__interrupt__":
                    yield format_sse("node_done", {
                        "node": "human_approval",
                        "output": {"status": "paused"},
                        "duration_ms": 0,
                    })
                    continue

                yield format_sse("node_start", {"node": node_name, "timestamp": t0})

                if node_name == "code_agent" and update.get("tool_calls"):
                    for tc in update["tool_calls"]:
                        if tc.get("status") == "pending":
                            yield format_sse("tool_call", {
                                "id": tc.get("id"),
                                "tool_name": tc.get("tool_name"),
                                "arguments": tc.get("arguments"),
                            })

                if node_name == "tool_node" and update.get("tool_results"):
                    for r in update["tool_results"]:
                        yield format_sse("tool_result", {
                            "tool_name": r.get("tool_name"),
                            "success": r.get("success"),
                            "output": str(r.get("output", ""))[:300],
                        })

                duration = (time.time() - t0) * 1000
                yield format_sse("node_done", {
                    "node": node_name,
                    "output": _sanitize(node_name, update),
                    "duration_ms": round(duration, 1),
                })

    except Exception as exc:
        if "GraphInterrupt" in type(exc).__name__ or "interrupt" in str(exc).lower():
            pass
        else:
            yield format_sse("error", {"message": str(exc)})
            return

    # Re-check for interrupt (human_approval may be hit again after reject→loop)
    snap = await graph.aget_state(config)
    if snap and snap.interrupts:
        interrupt_data = snap.interrupts[0].value if snap.interrupts else {}
        yield format_sse("interrupt", {
            "thread_id": thread_id,
            "actions": interrupt_data.get("actions", []),
            "message": interrupt_data.get("message", ""),
        })
    else:
        yield format_sse("done", {"thread_id": thread_id})
