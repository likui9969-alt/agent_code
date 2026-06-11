"""Pydantic models for FastAPI request / response serialisation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ApprovalAction = Literal["approved", "rejected", "modify"]


# ============================================================================
# Request schemas
# ============================================================================

class ChatRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=4000)
    thread_id: str | None = Field(None)
    project_path: str | None = Field(None, description="Absolute path to the open project directory.")


class ResumeRequest(BaseModel):
    action: ApprovalAction = Field(...)
    feedback: str = Field("", max_length=2000)
    project_path: str | None = Field(None, description="Updated project path (optional).")


class LLMSettingsRequest(BaseModel):
    api_key: str | None = Field(None, max_length=512)
    model: str | None = Field(None, max_length=64)


class LLMSettingsResponse(BaseModel):
    configured: bool
    model: str


# ============================================================================
# Building-blocks
# ============================================================================

class MessageSchema(BaseModel):
    role: str
    content: str


class ReviewSchema(BaseModel):
    passed: bool
    issues: list[str]


class InterruptSchema(BaseModel):
    type: str = "human_approval"
    message: str
    actions: list[str]
    code_preview: str = ""
    review: ReviewSchema


class ToolCallSchema(BaseModel):
    id: str
    tool_name: str
    arguments: dict
    result: dict | None = None
    status: str  # "pending" | "executed" | "error"


class MemoryStats(BaseModel):
    redis_enabled: bool = False
    messages_count: int = 0
    plan_versions: int = 0
    code_versions: int = 0
    review_count: int = 0


# ============================================================================
# Response schemas
# ============================================================================

class ChatResponse(BaseModel):
    status: Literal["completed"] = "completed"
    input: str
    plan: str
    code: str
    review: ReviewSchema
    iteration_count: int
    approval_status: str
    human_feedback: str
    tool_calls: list[ToolCallSchema] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    messages: list[MessageSchema]
    thread_id: str
    memory: MemoryStats = Field(default_factory=MemoryStats)


class PausedResponse(BaseModel):
    status: Literal["paused"] = "paused"
    thread_id: str
    interrupt: InterruptSchema
    state_summary: dict[str, Any] = Field(default_factory=dict)
    memory: MemoryStats = Field(default_factory=MemoryStats)


class StateResponse(BaseModel):
    status: Literal["idle", "paused", "completed"] = "idle"
    thread_id: str
    input: str
    plan: str
    code: str
    review: ReviewSchema
    iteration_count: int
    approval_status: str
    human_feedback: str
    tool_calls: list[ToolCallSchema] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    messages: list[MessageSchema]
    project_root: str = ""
    target_file: str = ""
    memory: MemoryStats = Field(default_factory=MemoryStats)


# ============================================================================
# Streaming event schemas (SSE payload shapes)
# ============================================================================


class ErrorResponse(BaseModel):
    """Returned when the agent pipeline stops due to an LLM error."""
    success: bool = False
    error: str
    detail: str = ""
    thread_id: str


class StreamEventSchema(BaseModel):
    """Shape of the JSON payload inside an SSE ``data:`` line."""

    event: str = Field(..., description="One of: start, node_start, node_done, tool_call, "
                       "tool_result, interrupt, resume, done, error")
    node: str | None = Field(None, description="Node name (for node_start / node_done).")
    thread_id: str | None = None
    timestamp: float | None = None
    output: dict[str, Any] | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    message: str | None = None
    duration_ms: float | None = None
