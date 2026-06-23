"""FastAPI application — HTTP interface with Redis + Tools + HITL."""

from __future__ import annotations

import hashlib
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.auth import require_auth
from app.config import settings
from app.graph import build_graph
from app.mcp.loader import mcp_loader
from app.memory import MemoryManager
from app.llm import configure as configure_llm
from app.rate_limit import RateLimitMiddleware, get_rate_limiter
from app.redis_client import close_async_redis, init_async_redis
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
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
_graph: CompiledStateGraph | None = None


def _get_graph() -> CompiledStateGraph:
    """Return the compiled LangGraph graph.

    In production the graph is built during lifespan startup (after Redis
    init).  When the lifespan hasn't run (e.g. tests with TestClient),
    the graph is built lazily on first access.
    """
    global _graph
    if _graph is None:
        logger.info("Graph not built by lifespan — building lazily (test mode)")
        _graph = build_graph()
    return _graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_ok, _graph
    # ── Startup ──
    if settings.redis_enabled:
        try:
            await init_async_redis()
            _redis_ok = True
        except Exception as exc:
            _redis_ok = False
            logger.warning("Redis unavailable, using in-memory fallback: %s", exc)

    # Load MCP plugins (FileMCP + GitMCP built-ins)
    result = mcp_loader.discover_and_load_all()
    for mcp_name, adapters in result.items():
        pass  # logged inside the loader

    # Build graph AFTER Redis init (so RedisSaver has a valid connection)
    _graph = build_graph()
    logger.info("Graph compiled — ready to serve requests")

    yield

    # ── Shutdown ──
    _graph = None
    await close_async_redis()


app = FastAPI(
    title="AI Code Assistant MVP",
    description="Planner → Code → Tools → Review → Human-in-the-Loop + Redis Memory",
    version="0.4.0",
    lifespan=lifespan,
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

# ── CORS middleware ─────────────────────────────────────────────────────
# Security: never combine allow_origins=["*"] with allow_credentials=True.
# Browsers (per the Fetch spec) reject such combinations; we enforce it here
# so a misconfigured env doesn't create a silently-insecure state.
_cors_origins = settings.cors_origins
_cors_credentials_allowed = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials_allowed,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Thread-ID"],
    expose_headers=["X-Thread-ID"],
    max_age=600,  # cache preflight for 10 minutes
)

# ── Rate-limit middleware (after CORS — preflight is free) ──────────────
app.add_middleware(
    RateLimitMiddleware,
    limiter=get_rate_limiter(),
    exempt={"/health"},
)


# ============================================================================
# Session ownership helpers
# ============================================================================


def _owner_hash(token: str) -> str | None:
    """Return a SHA-256 hash of the bearer token for session ownership.

    Returns ``None`` when auth is disabled (no ownership tracking needed).
    """
    if not token:
        return None
    return hashlib.sha256(token.encode()).hexdigest()


async def _verify_thread_ownership(thread_id: str, token: str) -> None:
    """Verify that *token* owns *thread_id*, or raise 403.

    Ownership is enforced only when ``API_AUTH_TOKEN`` is configured.
    When auth is disabled, all threads are public.
    """
    if not settings.api_auth_token:
        return  # Auth disabled — no ownership checks

    owner = _owner_hash(token)
    if not owner:
        return  # No token provided and auth is optional

    meta = await MemoryManager(thread_id).get_metadata()
    stored_owner = meta.get("owner")
    if stored_owner is None:
        return  # Thread was created before ownership was added — allow

    if stored_owner != owner:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not own this thread.",
        )


async def _set_thread_owner(thread_id: str, token: str) -> None:
    """Record *token* as the owner of *thread_id*."""
    if not settings.api_auth_token or not token:
        return
    await MemoryManager(thread_id).update_metadata(owner=_owner_hash(token))


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


async def _memory_stats(session_id: str) -> MemoryStats:
    return MemoryStats(**await MemoryManager(session_id).get_memory_stats())


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
        "error": "",
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


@app.post(
    "/chat",
    response_model=ChatResponse | PausedResponse | ErrorResponse,
    summary="Start AI agent pipeline",
    description=(
        "Send a user request to the AI agent pipeline. "
        "The pipeline runs: **Planner → Code Agent → (optional) Tool Execution → "
        "Reviewer → Human Approval**. "
        "If the reviewer passes, the pipeline pauses for human confirmation; "
        "the client must then call ``/chat/{thread_id}/resume`` to continue."
    ),
    responses={
        200: {"description": "Pipeline completed or paused for human approval"},
        401: {"description": "Missing or invalid API token"},
        403: {"description": "Thread ownership mismatch"},
        500: {"description": "Internal error (LLM failure, graph error, etc.)"},
    },
)
async def chat(request: ChatRequest, _token: str = Depends(require_auth)) -> ChatResponse | PausedResponse | ErrorResponse:
    # If the caller provides an existing thread_id, verify ownership first.
    if request.thread_id:
        await _verify_thread_ownership(request.thread_id, _token)
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    await MemoryManager(thread_id).update_metadata(task=request.input[:200])
    await MemoryManager(thread_id).add_message("human", request.input, agent="user")
    await MemoryManager(thread_id).set_status("running")
    await _set_thread_owner(thread_id, _token)
    _bind_project_root(request.project_path)

    try:
        result = await _get_graph().ainvoke(
            _initial_state(request.input, thread_id, request.project_path), config
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph error: {exc}") from exc

    # ── Error check ──
    if result.get("error"):
        await MemoryManager(thread_id).set_status("error")
        return ErrorResponse(
            success=False,
            error=result["error"],
            detail="The AI agent pipeline stopped due to an LLM error. "
                   "Check that QWEN_API_KEY is configured correctly.",
            thread_id=thread_id,
        )

    # Interrupt check
    snap = await _get_graph().aget_state(config)
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
            memory=await _memory_stats(thread_id),
        )

    await MemoryManager(thread_id).set_status("completed")
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
        memory=await _memory_stats(thread_id),
    )


@app.post(
    "/chat/{thread_id}/resume",
    response_model=ChatResponse | PausedResponse | ErrorResponse,
    summary="Resume paused agent pipeline",
    description=(
        "Resume a paused agent pipeline with a human decision. "
        "Valid actions: ``approved``, ``rejected``, ``modify``. "
        "If ``modify``, provide ``feedback`` to guide the rework."
    ),
    responses={
        200: {"description": "Pipeline completed or paused again"},
        400: {"description": "Thread is not paused"},
        404: {"description": "Thread not found"},
        401: {"description": "Missing or invalid API token"},
        403: {"description": "Thread ownership mismatch"},
        500: {"description": "Internal error"},
    },
)
async def resume(thread_id: str, body: ResumeRequest, _token: str = Depends(require_auth)) -> ChatResponse | PausedResponse | ErrorResponse:
    await _verify_thread_ownership(thread_id, _token)
    config = {"configurable": {"thread_id": thread_id}}

    snap = await _get_graph().aget_state(config)
    if snap is None or snap.values is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not snap.interrupts:
        raise HTTPException(status_code=400, detail="Thread is not paused")

    await MemoryManager(thread_id).set_status("running")
    project_path = body.project_path or (snap.values or {}).get("project_root", "")
    _bind_project_root(project_path or None)

    try:
        result = await _get_graph().ainvoke(
            Command(resume={"action": body.action, "feedback": body.feedback}), config
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume error: {exc}") from exc

    # ── Error check ──
    if result.get("error"):
        await MemoryManager(thread_id).set_status("error")
        return ErrorResponse(
            success=False,
            error=result["error"],
            detail="The AI agent pipeline stopped due to an LLM error. "
                   "Check that QWEN_API_KEY is configured correctly.",
            thread_id=thread_id,
        )

    snap = await _get_graph().aget_state(config)
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
            memory=await _memory_stats(thread_id),
        )

    await MemoryManager(thread_id).set_status("completed")
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
        memory=await _memory_stats(thread_id),
    )


@app.get("/chat/{thread_id}/state", response_model=StateResponse)
async def get_state(thread_id: str, _token: str = Depends(require_auth)):
    await _verify_thread_ownership(thread_id, _token)
    config = {"configurable": {"thread_id": thread_id}}
    snap = await _get_graph().aget_state(config)
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
        memory=await _memory_stats(thread_id),
    )


@app.get("/chat/{thread_id}/memory")
async def get_memory(thread_id: str, _token: str = Depends(require_auth)):
    await _verify_thread_ownership(thread_id, _token)
    memory = MemoryManager(thread_id)
    return {
        "thread_id": thread_id,
        "stats": await memory.get_memory_stats(),
        "recent_messages": await memory.get_messages(limit=10),
    }


# ============================================================================
# Streaming endpoints (SSE)
# ============================================================================


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, _token: str = Depends(require_auth)):
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
    # If the caller provides an existing thread_id, verify ownership first.
    if request.thread_id:
        await _verify_thread_ownership(request.thread_id, _token)
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial = _initial_state(request.input, thread_id, request.project_path)

    # Init memory
    await MemoryManager(thread_id).add_message("human", request.input, agent="user")
    await MemoryManager(thread_id).set_status("streaming")
    await _set_thread_owner(thread_id, _token)

    return StreamingResponse(
        stream_chat(_get_graph(), initial, config, thread_id, request.project_path),
        media_type="text/event-stream",
        headers={
            "X-Thread-ID": thread_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/chat/{thread_id}/resume/stream")
async def resume_stream(thread_id: str, body: ResumeRequest, _token: str = Depends(require_auth)):
    """Resume a paused graph and stream the remaining events as SSE.

    Must be called after ``/chat/stream`` returned an ``interrupt`` event.
    """
    config = {"configurable": {"thread_id": thread_id}}

    await _verify_thread_ownership(thread_id, _token)

    # Validate
    snap = await _get_graph().aget_state(config)
    if snap is None or snap.values is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not snap.interrupts:
        raise HTTPException(status_code=400, detail="Thread is not paused")

    await MemoryManager(thread_id).set_status("streaming")
    project_path = body.project_path or snap.values.get("project_root", "")

    return StreamingResponse(
        stream_resume(_get_graph(), config, thread_id, body, project_path),
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
async def list_tools(_token: str = Depends(require_auth)):
    """Return all registered tools (native + MCP) and their schemas."""
    return {
        "tools": tool_registry.list_tools(),
        "by_source": tool_registry.list_tools_by_source(),
        "schemas": tool_registry.get_all_schemas(),
    }


@app.get("/mcp")
async def list_mcps(_token: str = Depends(require_auth)):
    """Return loaded MCP plugins and per-plugin tool lists."""
    return {
        "mcps": mcp_loader.list_loaded(),
        "tool_count": len(tool_registry.list_tools()),
    }


@app.post("/mcp/{name}/reload")
async def reload_mcp(name: str, _token: str = Depends(require_auth)):
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
async def update_llm_settings(body: LLMSettingsRequest, _token: str = Depends(require_auth)):
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
