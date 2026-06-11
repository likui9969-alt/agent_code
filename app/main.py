"""FastAPI application — HTTP interface with Redis + Tools + HITL."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.config import settings
from app.graph import build_graph
from app.mcp.loader import mcp_loader
from app.memory import MemoryManager, close_redis_pool, init_redis_pool
from app.llm import configure as configure_llm
from app.schemas import (
    ChatRequest,
    ChatResponse,
    InterruptSchema,
    LLMSettingsRequest,
    LLMSettingsResponse,
    MemoryStats,
    MessageSchema,
    PausedResponse,
    ResumeRequest,
    ReviewSchema,
    StateResponse,
    ToolCallSchema,
)
from app.streaming import stream_chat, stream_resume
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)
_redis_ok = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_ok
    # ── Startup ──
    if settings.redis_enabled:
        try:
            init_redis_pool()
            _redis_ok = True
        except Exception as exc:
            _redis_ok = False
            logger.warning("Redis unavailable, using in-memory fallback: %s", exc)

    # Load MCP plugins (FileMCP + GitMCP built-ins)
    result = mcp_loader.discover_and_load_all()
    for mcp_name, adapters in result.items():
        pass  # logged inside the loader

    yield

    # ── Shutdown ──
    close_redis_pool()


app = FastAPI(
    title="AI Code Assistant MVP",
    description="Planner → Code → Tools → Review → Human-in-the-Loop + Redis Memory",
    version="0.4.0",
    lifespan=lifespan,
)

graph = build_graph()


# ============================================================================
# Helpers
# ============================================================================

def _serialize(messages: list) -> list[MessageSchema]:
    return [
        MessageSchema(
            role=type(msg).__name__.replace("Message", "").lower(),
            content=str(msg.content),
        )
        for msg in messages
    ]


def _build_review(review_raw: dict) -> ReviewSchema:
    return ReviewSchema(
        passed=review_raw.get("passed", False),
        issues=review_raw.get("issues", []),
    )


def _memory_stats(session_id: str) -> MemoryStats:
    return MemoryStats(**MemoryManager(session_id).get_memory_stats())


def _tool_calls_schema(calls: list[dict]) -> list[ToolCallSchema]:
    return [ToolCallSchema(**tc) for tc in calls]


def _initial_state(user_input: str, thread_id: str, project_path: str | None = None) -> dict:
    return {
        "session_id": thread_id,
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
        "project_root": project_path or "",
        "target_file": "output.py",
    }


def _bind_project_root(project_path: str | None) -> None:
    from app.project_workspace import set_project_root
    set_project_root(project_path or None)


# ============================================================================
# Routes
# ============================================================================


@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse | PausedResponse:
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    MemoryManager(thread_id).update_metadata(task=request.input[:200])
    MemoryManager(thread_id).add_message("human", request.input, agent="user")
    MemoryManager(thread_id).set_status("running")
    _bind_project_root(request.project_path)

    try:
        result = await graph.ainvoke(
            _initial_state(request.input, thread_id, request.project_path), config
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph error: {exc}") from exc

    # Interrupt check
    snap = await graph.aget_state(config)
    if snap and snap.interrupts:
        data = snap.interrupts[0].value if snap.interrupts else {}
        return PausedResponse(
            thread_id=thread_id,
            interrupt=InterruptSchema(
                type=data.get("type", "human_approval"),
                message=data.get("message", ""),
                actions=data.get("actions", []),
                code_preview=result.get("code", "")[:500],
                review=_build_review(result.get("review", {})),
            ),
            state_summary={
                "plan": result.get("plan", ""),
                "iteration_count": result.get("iteration_count", 0),
            },
            memory=_memory_stats(thread_id),
        )

    MemoryManager(thread_id).set_status("completed")
    return ChatResponse(
        input=request.input,
        plan=result.get("plan", ""),
        code=result.get("code", ""),
        review=_build_review(result.get("review", {})),
        iteration_count=result.get("iteration_count", 0),
        approval_status=result.get("approval_status", "pending"),
        human_feedback=result.get("human_feedback", ""),
        tool_calls=_tool_calls_schema(result.get("tool_calls", [])),
        tool_results=result.get("tool_results", []),
        messages=_serialize(result.get("messages", [])),
        thread_id=thread_id,
        memory=_memory_stats(thread_id),
    )


@app.post("/chat/{thread_id}/resume")
async def resume(thread_id: str, body: ResumeRequest) -> ChatResponse | PausedResponse:
    config = {"configurable": {"thread_id": thread_id}}

    snap = await graph.aget_state(config)
    if snap is None or snap.values is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not snap.interrupts:
        raise HTTPException(status_code=400, detail="Thread is not paused")

    MemoryManager(thread_id).set_status("running")
    project_path = body.project_path or (snap.values or {}).get("project_root", "")
    _bind_project_root(project_path or None)

    try:
        result = await graph.ainvoke(
            Command(resume={"action": body.action, "feedback": body.feedback}), config
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume error: {exc}") from exc

    snap = await graph.aget_state(config)
    if snap and snap.interrupts:
        data = snap.interrupts[0].value if snap.interrupts else {}
        return PausedResponse(
            thread_id=thread_id,
            interrupt=InterruptSchema(
                type=data.get("type", "human_approval"),
                message=data.get("message", ""),
                actions=data.get("actions", []),
                code_preview=result.get("code", "")[:500],
                review=_build_review(result.get("review", {})),
            ),
            state_summary={
                "plan": result.get("plan", ""),
                "iteration_count": result.get("iteration_count", 0),
            },
            memory=_memory_stats(thread_id),
        )

    MemoryManager(thread_id).set_status("completed")
    return ChatResponse(
        input=snap.values.get("input", ""),
        plan=result.get("plan", ""),
        code=result.get("code", ""),
        review=_build_review(result.get("review", {})),
        iteration_count=result.get("iteration_count", 0),
        approval_status=result.get("approval_status", "pending"),
        human_feedback=result.get("human_feedback", ""),
        tool_calls=_tool_calls_schema(result.get("tool_calls", [])),
        tool_results=result.get("tool_results", []),
        messages=_serialize(result.get("messages", [])),
        thread_id=thread_id,
        memory=_memory_stats(thread_id),
    )


@app.get("/chat/{thread_id}/state", response_model=StateResponse)
async def get_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(config)
    if snap is None or snap.values is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    values = snap.values
    status = "paused" if snap.interrupts else (
        "completed" if values.get("approval_status") == "approved" else "idle"
    )
    return StateResponse(
        status=status,
        thread_id=thread_id,
        input=values.get("input", ""),
        plan=values.get("plan", ""),
        code=values.get("code", ""),
        review=_build_review(values.get("review", {})),
        iteration_count=values.get("iteration_count", 0),
        approval_status=values.get("approval_status", "pending"),
        human_feedback=values.get("human_feedback", ""),
        tool_calls=_tool_calls_schema(values.get("tool_calls", [])),
        tool_results=values.get("tool_results", []),
        messages=_serialize(values.get("messages", [])),
        project_root=values.get("project_root", ""),
        target_file=values.get("target_file", ""),
        memory=_memory_stats(thread_id),
    )


@app.get("/chat/{thread_id}/memory")
async def get_memory(thread_id: str):
    memory = MemoryManager(thread_id)
    return {
        "thread_id": thread_id,
        "stats": memory.get_memory_stats(),
        "recent_messages": memory.get_messages(limit=10),
    }


# ============================================================================
# Streaming endpoints (SSE)
# ============================================================================


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Run the agent pipeline and stream every node output as SSE.

    Returns ``text/event-stream``.  Events emitted:

    - ``start``, ``node_start``, ``node_done``
    - ``tool_call``, ``tool_result``
    - ``interrupt`` (graph paused for human)
    - ``done`` (graph completed)
    - ``error``

    Usage::

        curl -N -X POST http://localhost:8000/chat/stream \\
          -H "Content-Type: application/json" \\
          -d '{"input": "Write a quicksort function"}'
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial = _initial_state(request.input, thread_id, request.project_path)

    # Init memory
    MemoryManager(thread_id).add_message("human", request.input, agent="user")
    MemoryManager(thread_id).set_status("streaming")

    return StreamingResponse(
        stream_chat(graph, initial, config, thread_id, request.project_path),
        media_type="text/event-stream",
        headers={
            "X-Thread-ID": thread_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/chat/{thread_id}/resume/stream")
async def resume_stream(thread_id: str, body: ResumeRequest):
    """Resume a paused graph and stream the remaining events as SSE.

    Must be called after ``/chat/stream`` returned an ``interrupt`` event.
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Validate
    snap = await graph.aget_state(config)
    if snap is None or snap.values is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not snap.interrupts:
        raise HTTPException(status_code=400, detail="Thread is not paused")

    MemoryManager(thread_id).set_status("streaming")
    project_path = body.project_path or snap.values.get("project_root", "")

    return StreamingResponse(
        stream_resume(graph, config, thread_id, body, project_path),
        media_type="text/event-stream",
        headers={
            "X-Thread-ID": thread_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================================
# Tools & MCP introspection
# ============================================================================


@app.get("/tools")
async def list_tools():
    """Return all registered tools (native + MCP) and their schemas."""
    return {
        "tools": tool_registry.list_tools(),
        "by_source": tool_registry.list_tools_by_source(),
        "schemas": tool_registry.get_all_schemas(),
    }


@app.get("/mcp")
async def list_mcps():
    """Return loaded MCP plugins and per-plugin tool lists."""
    return {
        "mcps": mcp_loader.list_loaded(),
        "tool_count": len(tool_registry.list_tools()),
    }


@app.post("/mcp/{name}/reload")
async def reload_mcp(name: str):
    """Reload a single MCP plugin by name."""
    result = mcp_loader.reload(name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not loaded")
    return {
        "status": "reloaded",
        "name": name,
        "tool_count": len(result),
        "tools": [a.name for a in result],
    }


@app.post("/settings/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(body: LLMSettingsRequest):
    """Accept API key / model from the Streamlit settings page."""
    if not body.api_key and not body.model:
        raise HTTPException(status_code=400, detail="Provide api_key and/or model")
    configure_llm(api_key=body.api_key, model=body.model)
    return LLMSettingsResponse(
        configured=bool(settings.qwen_api_key),
        model=settings.qwen_model,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "redis_enabled": settings.redis_enabled,
        "redis_connected": _redis_ok if settings.redis_enabled else None,
        "llm_configured": bool(settings.qwen_api_key),
    }
