"""Agent node implementations with Redis memory + Tool integration.

Every node follows the **Read → Execute → Write** pattern.

Tool-aware nodes (code_agent) emit ``tool_calls`` in the state; the dedicated
:func:`tool_node` executes them via :class:`ToolRegistry`.
"""

import asyncio
import uuid

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from app.llm import (
    PLANNER_SYSTEM,
    CODER_SYSTEM,
    CODER_FIX_SYSTEM,
    REVIEWER_SYSTEM,
    LLMError,
    chat,
    wrap_user_input,
)
from app.memory import MemoryManager
from app.state import AgentState, ReviewResult, ToolCall
from app.tools.registry import tool_registry


# ============================================================================
# LLM call helpers
# ============================================================================

import json as _json


def llm_planner(user_input: str, _ctx: dict | None = None) -> str:
    """Generate a plan using the Qwen API."""
    return chat(PLANNER_SYSTEM, wrap_user_input(user_input))


def _safe_issues(review: ReviewResult | None) -> list[str]:
    """Safely extract a list of issue strings from a review result.

    Handles malformed data from the LLM (missing key, None, non-list values)
    by falling back to an empty list so the pipeline can proceed.
    """
    if not isinstance(review, dict):
        return []
    raw = review.get("issues")
    if isinstance(raw, list):
        return [str(i) for i in raw if i]
    return []


def llm_coder(
    plan: str, user_input: str,
    review: ReviewResult | None = None,
    human_feedback: str = "",
) -> str:
    """Generate code using the Qwen API."""
    issues = _safe_issues(review)
    system = CODER_FIX_SYSTEM if (issues or human_feedback) else CODER_SYSTEM
    prompt = f"Plan:\n{plan}\n\n"
    if human_feedback:
        prompt += f"Human feedback:\n{human_feedback}\n\n"
    if issues:
        prompt += f"Issues to fix:\n" + "\n".join(f"- {i}" for i in issues)
    prompt += f"\n{wrap_user_input(user_input)}"
    reply = chat(system, prompt, max_tokens=4096)
    return _extract_code_block(reply)


def llm_reviewer(code: str, user_input: str, iteration: int) -> ReviewResult:
    """Review code using the Qwen API."""
    reply = chat(REVIEWER_SYSTEM, f"{wrap_user_input(user_input)}\n\nCode:\n```python\n{code}\n```")
    try:
        result = _json.loads(_extract_json(reply))
        return ReviewResult(
            passed=bool(result.get("passed", False)),
            issues=list(result.get("issues", [])),
        )
    except (_json.JSONDecodeError, KeyError) as exc:
        raise LLMError(
            "Failed to parse reviewer response",
            f"The LLM returned malformed JSON: {exc}",
        ) from exc


def _extract_code_block(text: str) -> str:
    """Extract code from a markdown code block, or return text as-is."""
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Remove language tag
                nl = part.find("\n")
                return part[nl + 1:] if nl != -1 else part
    return text.strip()


def _extract_json(text: str) -> str:
    """Extract JSON object from text (may be wrapped in markdown)."""
    text = text.strip()
    if "```" in text:
        text = _extract_code_block(text)
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


# ============================================================================
# Helpers
# ============================================================================


def _normalize_code(source: str) -> str:
    """Normalize Python source for fuzzy comparison.

    Operations:
    1. Normalize line endings to ``\\n``.
    2. Strip trailing whitespace from each line.
    3. Strip leading / trailing blank lines.

    This makes the comparison tolerant of whitespace formatting
    differences introduced by LLM re-generation, preventing the
    code_agent → tool_node infinite loop when the LLM produces
    semantically identical but whitespace-different code.
    """
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Strip trailing whitespace per line
    lines = [l.rstrip() for l in lines]
    # Strip leading blank lines
    while lines and lines[0] == "":
        lines.pop(0)
    # Strip trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _code_equivalent(a: str, b: str) -> bool:
    """Return ``True`` if *a* and *b* are equivalent after normalization."""
    return _normalize_code(a) == _normalize_code(b)


def _path_equivalent(a: str, b: str) -> bool:
    """Return ``True`` if two file paths refer to the same location."""
    return a.replace("\\", "/").strip("/") == b.replace("\\", "/").strip("/")


def _write_done(state: AgentState, code: str, target: str) -> bool:
    """True if the current *code* was already written to *target* on disk."""
    for r in reversed(state.get("tool_results", [])):
        if r.get("tool_name") != "write_file":
            continue
        args = r.get("arguments", {})
        return (
            r.get("success")
            and _path_equivalent(args.get("path", ""), target)
            and _code_equivalent(args.get("content", ""), code)
        )
    return False


def _run_done(state: AgentState, code: str, target: str) -> bool:
    """True if *target* was at least *attempted* after the latest write of *code*."""
    results = state.get("tool_results", [])
    write_idx = -1
    for i, r in enumerate(results):
        if r.get("tool_name") != "write_file" or not r.get("success"):
            continue
        args = r.get("arguments", {})
        if _path_equivalent(args.get("path", ""), target) and _code_equivalent(args.get("content", ""), code):
            write_idx = i
    if write_idx < 0:
        return False
    for r in results[write_idx + 1:]:
        if r.get("tool_name") != "run_python":
            continue
        args = r.get("arguments", {})
        # Return True if we attempted to run — don't loop forever on failure
        return _path_equivalent(args.get("file_path", ""), target)
    return False

def _make_tool_call(name: str, args: dict) -> ToolCall:
    return ToolCall(
        id=str(uuid.uuid4())[:8],
        tool_name=name,
        arguments=args,
        result=None,
        status="pending",
    )


def _target_file(state: AgentState) -> str:
    """Resolve the relative path where generated code should be written."""
    if state.get("target_file"):
        return state["target_file"]
    return "output.py"


# ============================================================================
# LangGraph node functions
# ============================================================================

async def planner_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    await memory.build_context()

    try:
        plan = llm_planner(state["input"])
    except LLMError as exc:
        await memory.add_message("system", f"[Error] Planner: {exc}", agent="system")
        await memory.set_status("error")
        return {
            "error": str(exc),
            "plan": "",
            "tool_calls": [],
            "messages": [AIMessage(content=f"[Error] Planner failed — {exc}")],
        }

    await memory.save_plan(plan)
    await memory.add_message("ai", f"[Planner]\n{plan}", agent="planner")
    await memory.set_status("planning")

    return {
        "plan": plan,
        "tool_calls": [],
        "messages": [AIMessage(content=f"[Planner]\n{plan}")],
    }


async def code_agent_node(state: AgentState) -> dict:
    """**Code Agent** — generate code + request tool executions.

    Tool orchestration::

        1. If code hasn't been written to disk → request ``write_file``.
        2. If written but not tested           → request ``run_python``.
        3. If both done                        → no tools → proceed to reviewer.
    """
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    await memory.build_context()

    review = state.get("review", {})
    feedback = state.get("human_feedback", "")

    # ── Generate / fix code ──
    try:
        code = llm_coder(
            state.get("plan", ""), state.get("input", ""), review,
            human_feedback=feedback,
        )
    except LLMError as exc:
        await memory.add_message("system", f"[Error] CodeAgent: {exc}", agent="system")
        await memory.set_status("error")
        return {
            "error": str(exc),
            "code": state.get("code", ""),
            "tool_calls": [],
            "messages": [AIMessage(content=f"[Error] CodeAgent failed — {exc}")],
        }

    # ── Decide which tools to call next (requires open project directory) ──
    target = _target_file(state)
    pending: list[ToolCall] = []
    has_project = bool(state.get("project_root"))
    if has_project and not _write_done(state, code, target):
        pending.append(_make_tool_call("write_file", {
            "path": target, "content": code,
        }))
    elif has_project and not _run_done(state, code, target):
        pending.append(_make_tool_call("run_python", {
            "file_path": target,
        }))

    # ── Persist ──
    issues = _safe_issues(review)
    trigger = "human_fix" if feedback else ("auto_fix" if issues else "initial")
    await memory.save_code(code, trigger=trigger)
    await memory.set_status("coding")

    tag = "[CodeAgent]"
    if feedback:
        tag = "[CodeAgent • human-fix]"
    elif issues:
        tag = "[CodeAgent • auto-fix]"

    msg = f"{tag}\n```python\n{code}\n```"
    if pending:
        names = [t["tool_name"] for t in pending]
        msg += f"\n\n[Tool requests] → {', '.join(names)}"
    elif not has_project:
        msg += "\n\n[Note] 未打开项目目录，请先在侧边栏打开项目或使用「应用到项目」。"

    await memory.add_message("ai", msg, agent="code_agent")

    return {
        "code": code,
        "target_file": target,
        "tool_calls": pending,
        "messages": [AIMessage(content=msg)],
    }


async def tool_node(state: AgentState) -> dict:
    """**Tool Executor** — run all pending ``tool_calls`` via the registry.

    Each pending call is executed; results are written to ``tool_results``
    (append-only) and the ``tool_calls`` list is returned with status updated.
    """
    calls: list[ToolCall] = state.get("tool_calls", [])
    results: list[dict] = []
    executed: list[ToolCall] = []
    project_root = state.get("project_root") or None

    for tc in calls:
        if tc.get("status") != "pending":
            executed.append(tc)
            continue

        result = await asyncio.to_thread(
            tool_registry.execute,
            tc["tool_name"],
            tc.get("arguments", {}),
            project_root=project_root,
        )
        result_dict = result.to_dict()
        result_dict["tool_name"] = tc["tool_name"]
        result_dict["arguments"] = tc.get("arguments", {})

        tc_update: ToolCall = {
            **tc,
            "result": result_dict,
            "status": "executed" if result.success else "error",
        }
        executed.append(tc_update)
        results.append(result_dict)

    return {
        "tool_calls": executed,
        "tool_results": results,
        "messages": [
            AIMessage(
                content=f"[ToolNode] executed {len(results)} tool(s): "
                + ", ".join(
                    f"{r['tool_name']}={'OK' if r['success'] else 'FAIL'}"
                    for r in results
                )
            )
        ],
    }


async def reviewer_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    await memory.build_context()

    iteration = state.get("iteration_count", 0)
    try:
        review = llm_reviewer(state.get("code", ""), state.get("input", ""), iteration)
    except LLMError as exc:
        await memory.add_message("system", f"[Error] Reviewer: {exc}", agent="system")
        await memory.set_status("error")
        return {
            "error": str(exc),
            "review": state.get("review", {"passed": False, "issues": []}),
            "iteration_count": iteration + 1,
            "messages": [AIMessage(content=f"[Error] Reviewer failed — {exc}")],
        }

    await memory.save_review(review, iteration)
    await memory.add_message(
        "ai",
        f"[Reviewer] iter={iteration} {'PASSED' if review.get('passed') else 'FAILED'}",
        agent="reviewer",
    )
    await memory.set_status("reviewing")

    verdict = "PASSED" if review.get("passed") else "FAILED"
    issues = _safe_issues(review)
    detail = (
        "\n".join(f"  - {i}" for i in issues)
        if issues else "  (none)"
    )

    return {
        "review": review,
        "iteration_count": iteration + 1,
        "messages": [
            AIMessage(content=f"[Reviewer] iter={iteration} {verdict}\nIssues:\n{detail}")
        ],
    }


async def human_approval_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    await memory.build_context()

    await memory.set_status("paused")
    decision = interrupt({
        "type": "human_approval",
        "message": "Please review the generated code and choose an action.",
        "actions": ["approved", "rejected", "modify"],
        "code": state.get("code", ""),
        "review": state.get("review", {}),
    })

    action = decision.get("action", "approved")
    feedback = decision.get("feedback", "")

    await memory.add_message("human", f"{action}: {feedback}", agent="human")
    await memory.set_status("approved" if action == "approved" else "rejected")

    label = {"approved": "APPROVED", "rejected": "REJECTED", "modify": "MODIFY"}.get(action, action)

    return {
        "approval_status": action,
        "human_feedback": feedback,
        "messages": [
            AIMessage(content=f"[Human] {label} | feedback: {feedback or '(none)'}")
        ],
    }
