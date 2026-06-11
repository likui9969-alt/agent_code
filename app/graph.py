"""LangGraph graph builder with tool-execution loop.

Topology (v4)::

    START
      │
      ▼
    planner
      │
      ▼
    code_agent ◄─────────────────────────────┐
      │                                       │
      ├── has pending tool_calls? ──► tool_node ──┘
      │ (no tools)                            │
      ▼                                       │
    reviewer ───(auto-fix loop ≤2)────────────┘
      │
      │ (passed or exhausted)
      ▼
    human_approval ★ INTERRUPT ★
      │
      ├── approved ──► END
      └── reject/modify ──► code_agent
"""

from langgraph.graph import END, START, StateGraph

from app.agents import (
    code_agent_node,
    human_approval_node,
    planner_node,
    reviewer_node,
    tool_node,
)
from app.state import AgentState

_MAX_REVIEW_ITERATIONS = 2


# ============================================================================
# Routing functions
# ============================================================================

def _route_after_planner(state: AgentState) -> str:
    """If planner errored, end immediately; otherwise proceed to code_agent."""
    if state.get("error"):
        return END
    return "code_agent"


def _route_after_code_agent(state: AgentState) -> str:
    """If code_agent errored, end immediately; otherwise route normally."""
    if state.get("error"):
        return END
    for tc in state.get("tool_calls", []):
        if tc.get("status") == "pending":
            return "tool_node"
    return "reviewer"


def _route_after_review(state: AgentState) -> str:
    """If reviewer errored, end immediately; otherwise route normally."""
    if state.get("error"):
        return END
    review = state.get("review", {})
    if review.get("passed", False):
        return "human_approval"
    if state.get("iteration_count", 0) >= _MAX_REVIEW_ITERATIONS:
        return "human_approval"
    return "code_agent"


def _route_after_human(state: AgentState) -> str:
    if state.get("approval_status") == "approved":
        return END
    return "code_agent"


# ============================================================================
# Graph assembly
# ============================================================================

def build_graph() -> StateGraph:
    workflow: StateGraph = StateGraph(AgentState)

    # ── Nodes ──
    workflow.add_node("planner", planner_node)
    workflow.add_node("code_agent", code_agent_node)
    workflow.add_node("tool_node", tool_node)          # ★ NEW
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("human_approval", human_approval_node)

    # ── Edges ──
    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"code_agent": "code_agent", END: END},
    )

    # Code agent → tool loop OR reviewer OR end (error)
    workflow.add_conditional_edges(
        "code_agent",
        _route_after_code_agent,
        {"tool_node": "tool_node", "reviewer": "reviewer", END: END},
    )
    workflow.add_edge("tool_node", "code_agent")       # always loop back

    # Reviewer → auto-fix OR human OR end (error)
    workflow.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"code_agent": "code_agent", "human_approval": "human_approval", END: END},
    )

    # Human → finish OR loop back
    workflow.add_conditional_edges(
        "human_approval",
        _route_after_human,
        {"code_agent": "code_agent", END: END},
    )

    from app.redis_saver import RedisSaver
    return workflow.compile(checkpointer=RedisSaver())
