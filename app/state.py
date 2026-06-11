"""LangGraph AgentState — the single source of truth flowing through the graph.

State field semantics
---------------------
- **overwrite** (default): each node writes the latest value.
- **add_messages** (append-only): messages accumulate across the run.
- **operator.add** (append-only): tool_calls_log and tool_results accumulate.
"""

from operator import add as _add
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ReviewResult(TypedDict):
    passed: bool
    issues: list[str]


class ToolCall(TypedDict, total=False):
    """One tool-call request or executed entry.

    When *status* is ``"pending"`` the call has not been executed yet.
    The :func:`tool_node` sets it to ``"executed"`` or ``"error"`` and
    populates *result*.
    """

    id: str
    tool_name: str
    arguments: dict
    result: dict | None  # ToolResult.to_dict()
    status: str  # "pending" | "executed" | "error"


class AgentState(TypedDict):
    """Shared state that travels through every LangGraph node.

    Attributes:
        session_id:       Redis session key (== thread_id).
        input:            Raw user request.
        plan:             Structured plan from Planner.
        code:             Latest code from Code agent.
        review:           Latest automated review verdict.
        iteration_count:  Review→fix cycles completed.
        human_feedback:   Free-text feedback from human reviewer.
        approval_status:  ``"pending"`` | ``"approved"`` | ``"rejected"`` | ``"modify"``.
        tool_calls:       Current batch of tool requests (overwrite).
        tool_results:     Accumulated tool execution results (append-only).
        messages:         Append-only conversation history.
        project_root:     Absolute path to the user's open project directory.
        target_file:      Relative path of the file the agent is writing.
    """

    session_id: str
    input: str
    plan: str
    code: str
    review: ReviewResult
    iteration_count: int
    human_feedback: str
    approval_status: str
    error: str
    tool_calls: list[ToolCall]
    tool_results: Annotated[list[dict], _add]
    messages: Annotated[list[BaseMessage], add_messages]
    project_root: str
    target_file: str
