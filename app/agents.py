"""Agent node implementations with Redis memory + Tool integration.

Every node follows the **Read → Execute → Write** pattern.

Tool-aware nodes (code_agent) emit ``tool_calls`` in the state; the dedicated
:func:`tool_node` executes them via :class:`ToolRegistry`.
"""

import uuid

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from app.memory import MemoryManager
from app.state import AgentState, ReviewResult, ToolCall
from app.tools.registry import tool_registry


# ============================================================================
# LLM — Real Qwen API + mock fallback
# ============================================================================

import json as _json

from app.llm import (
    PLANNER_SYSTEM,
    CODER_SYSTEM,
    CODER_FIX_SYSTEM,
    REVIEWER_SYSTEM,
    chat,
    is_available,
)


def llm_planner(user_input: str, _ctx: dict | None = None) -> str:
    """Generate a plan.  Tries real Qwen API first; falls back to mock."""
    if is_available():
        reply = chat(PLANNER_SYSTEM, user_input)
        if reply:
            return reply
    return _mock_planner(user_input)


def llm_coder(
    plan: str, user_input: str,
    review: ReviewResult | None = None,
    human_feedback: str = "",
) -> str:
    """Generate code.  Tries real Qwen API first; falls back to mock."""
    if is_available():
        system = CODER_FIX_SYSTEM if (review and review.get("issues")) or human_feedback else CODER_SYSTEM
        prompt = f"Plan:\n{plan}\n\n"
        if human_feedback:
            prompt += f"Human feedback:\n{human_feedback}\n\n"
        if review and review.get("issues"):
            prompt += f"Issues to fix:\n" + "\n".join(f"- {i}" for i in review["issues"])
        else:
            prompt += f"Request: {user_input}"
        reply = chat(system, prompt, max_tokens=4096)
        if reply:
            return _extract_code_block(reply)
    return _mock_coder(plan, user_input, review, human_feedback)


def llm_reviewer(code: str, user_input: str, iteration: int) -> ReviewResult:
    """Review code.  Tries real Qwen API first; falls back to mock."""
    if is_available():
        reply = chat(REVIEWER_SYSTEM, f"Request: {user_input}\n\nCode:\n```python\n{code}\n```")
        if reply:
            try:
                result = _json.loads(_extract_json(reply))
                return ReviewResult(
                    passed=bool(result.get("passed", False)),
                    issues=list(result.get("issues", [])),
                )
            except (_json.JSONDecodeError, KeyError):
                pass  # fall through to mock
    return _mock_reviewer(code, user_input, iteration)


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


# ── Mock fallback functions ──────────────────────────────────────────────────


def _mock_planner(user_input: str) -> str:
    lower = user_input.lower()
    if "sort" in lower or "排序" in lower:
        return _plan_sort(user_input)
    if "api" in lower or "fastapi" in lower or "接口" in lower:
        return _plan_api(user_input)
    if "fibonacci" in lower or "斐波那契" in lower:
        return _plan_fibonacci(user_input)
    return _plan_generic(user_input)


def _mock_coder(
    plan: str, user_input: str,
    review: ReviewResult | None = None,
    human_feedback: str = "",
) -> str:
    lower = user_input.lower()
    issues = (review or {}).get("issues", [])
    if "sort" in lower or "排序" in lower:
        return _code_sort()
    if "api" in lower or "fastapi" in lower or "接口" in lower:
        if human_feedback:
            return _code_api_v3(human_feedback)
        return _code_api_v2() if issues else _code_api_v1()
    if "fibonacci" in lower or "斐波那契" in lower:
        return _code_fibonacci()
    return _code_generic(user_input, human_feedback)


def _mock_reviewer(code: str, user_input: str, iteration: int) -> ReviewResult:
    lower = user_input.lower()
    if "api" in lower or "fastapi" in lower or "接口" in lower:
        if iteration == 0:
            return ReviewResult(
                passed=False,
                issues=[
                    "Missing PATCH /items/{item_id} endpoint",
                    "Missing DELETE /items/{item_id} endpoint",
                    "No rate-limiting middleware",
                ],
            )
        return ReviewResult(passed=True, issues=[])
    return ReviewResult(passed=True, issues=[])


# ── Planner helpers ────────────────────────────────────────────────────────

def _plan_sort(task: str) -> str:
    return (
        f"## Implementation Plan\n\n**Task**: {task}\n\n"
        f"1. **Algorithm**: QuickSort — O(n log n) average.\n"
        f"2. **Signature**: ``def quicksort(arr: list) -> list``.\n"
        f"3. **Logic**: base-case → pivot → partition → recurse.\n"
        f"4. **Edge cases**: empty, single, duplicates, already-sorted.\n"
        f"5. **Test**: 5 cases in ``__main__``."
    )


def _plan_api(task: str) -> str:
    return (
        f"## Implementation Plan\n\n**Task**: {task}\n\n"
        f"1. **Framework**: FastAPI + Pydantic v2.\n"
        f"2. **Routes**: full CRUD — GET /, POST/GET/PATCH/DELETE /items.\n"
        f"3. **Model**: Item with name, price (>0), optional description.\n"
        f"4. **Error handling**: HTTPException 400/404, rate-limit middleware.\n"
        f"5. **Run**: ``uvicorn main:app --reload``."
    )


def _plan_fibonacci(task: str) -> str:
    return (
        f"## Implementation Plan\n\n**Task**: {task}\n\n"
        f"1. **Algorithm**: Iterative — O(n) time, O(1) space.\n"
        f"2. **Signature**: ``def fibonacci(n: int) -> list[int]``.\n"
        f"3. **Edge cases**: n ≤ 0 → [], n = 1 → [0].\n"
        f"4. **Test**: first 10 = [0,1,1,2,3,5,8,13,21,34]."
    )


def _plan_generic(task: str) -> str:
    return (
        f"## Implementation Plan\n\n**Task**: {task}\n\n"
        f"1. **Analyse** requirements.\n2. **Design** signatures.\n"
        f"3. **Implement** + error handling + docstrings.\n"
        f"4. **Test** with representative inputs.\n5. **Document**."
    )


# ── Coder helpers ───────────────────────────────────────────────────────────

def _code_sort() -> str:
    return (
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
    )


def _code_api_v1() -> str:
    return (
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
    )


def _code_api_v2() -> str:
    return (
        "from fastapi import FastAPI, HTTPException, Request\n"
        "from pydantic import BaseModel, Field\nimport time\n\n\n"
        "app = FastAPI(title=\"Sample API\", version=\"2.0.0\")\n\n\n"
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
    )


def _code_api_v3(feedback: str) -> str:
    return (
        f"# ── v3: human-refined ──\n# Feedback: {feedback}\n\n"
        + _code_api_v2().replace("2.0.0", "3.0.0")
    )


def _code_fibonacci() -> str:
    return (
        "def fibonacci(n: int) -> list[int]:\n"
        '    """Return the first n Fibonacci numbers."""\n'
        "    if n <= 0:\n        return []\n"
        "    if n == 1:\n        return [0]\n"
        "    seq = [0, 1]\n"
        "    for _ in range(2, n):\n"
        "        seq.append(seq[-1] + seq[-2])\n"
        "    return seq\n\n\n"
        'if __name__ == "__main__":\n'
        '    print(fibonacci(10))\n'
    )


def _code_generic(task: str, feedback: str = "") -> str:
    comment = f"  # Human feedback: {feedback}" if feedback else ""
    return (
        f"def solution():\n"
        f'    """Solution for: {task}"""\n'
        f"    # 1. Parse & validate input{comment}\n"
        f"    # 2. Core logic\n# 3. Return result\n"
        f"    pass\n\n\n"
        f'if __name__ == "__main__":\n    solution()\n'
    )


# ============================================================================
# Helpers
# ============================================================================

def _write_done(state: AgentState, code: str, target: str) -> bool:
    """True if the current *code* was already written to *target* on disk."""
    for r in reversed(state.get("tool_results", [])):
        if r.get("tool_name") != "write_file":
            continue
        args = r.get("arguments", {})
        return (
            r.get("success")
            and args.get("path") == target
            and args.get("content") == code
        )
    return False


def _run_done(state: AgentState, code: str, target: str) -> bool:
    """True if *target* was executed after the latest successful write of *code*."""
    results = state.get("tool_results", [])
    write_idx = -1
    for i, r in enumerate(results):
        if r.get("tool_name") != "write_file" or not r.get("success"):
            continue
        args = r.get("arguments", {})
        if args.get("path") == target and args.get("content") == code:
            write_idx = i
    if write_idx < 0:
        return False
    for r in results[write_idx + 1:]:
        if r.get("tool_name") != "run_python":
            continue
        args = r.get("arguments", {})
        return r.get("success") and args.get("file_path") == target
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

def planner_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    memory.build_context()

    plan = llm_planner(state["input"])

    memory.save_plan(plan)
    memory.add_message("ai", f"[Planner]\n{plan}", agent="planner")
    memory.set_status("planning")

    return {
        "plan": plan,
        "tool_calls": [],
        "messages": [AIMessage(content=f"[Planner]\n{plan}")],
    }


def code_agent_node(state: AgentState) -> dict:
    """**Code Agent** — generate code + request tool executions.

    Tool orchestration (mock — in production the LLM decides)::

        1. If code hasn't been written to disk → request ``write_file``.
        2. If written but not tested           → request ``run_python``.
        3. If both done                        → no tools → proceed to reviewer.
    """
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    memory.build_context()

    review = state.get("review", {})
    feedback = state.get("human_feedback", "")

    # ── Generate / fix code ──
    code = llm_coder(
        state.get("plan", ""), state.get("input", ""), review,
        human_feedback=feedback,
    )

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
    trigger = "human_fix" if feedback else ("auto_fix" if review.get("issues") else "initial")
    memory.save_code(code, trigger=trigger)
    memory.set_status("coding")

    tag = "[CodeAgent]"
    if feedback:
        tag = "[CodeAgent • human-fix]"
    elif review.get("issues"):
        tag = "[CodeAgent • auto-fix]"

    msg = f"{tag}\n```python\n{code}\n```"
    if pending:
        names = [t["tool_name"] for t in pending]
        msg += f"\n\n[Tool requests] → {', '.join(names)}"
    elif not has_project:
        msg += "\n\n[Note] 未打开项目目录，请先在侧边栏打开项目或使用「应用到项目」。"

    memory.add_message("ai", msg, agent="code_agent")

    return {
        "code": code,
        "target_file": target,
        "tool_calls": pending,
        "messages": [AIMessage(content=msg)],
    }


def tool_node(state: AgentState) -> dict:
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

        result = tool_registry.execute(
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


def reviewer_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    memory.build_context()

    iteration = state.get("iteration_count", 0)
    review = llm_reviewer(state.get("code", ""), state.get("input", ""), iteration)

    memory.save_review(review, iteration)
    memory.add_message(
        "ai",
        f"[Reviewer] iter={iteration} {'PASSED' if review['passed'] else 'FAILED'}",
        agent="reviewer",
    )
    memory.set_status("reviewing")

    verdict = "PASSED" if review["passed"] else "FAILED"
    detail = (
        "\n".join(f"  - {i}" for i in review["issues"])
        if review["issues"] else "  (none)"
    )

    return {
        "review": review,
        "iteration_count": iteration + 1,
        "messages": [
            AIMessage(content=f"[Reviewer] iter={iteration} {verdict}\nIssues:\n{detail}")
        ],
    }


def human_approval_node(state: AgentState) -> dict:
    sid = state.get("session_id", "default")
    memory = MemoryManager(sid)
    memory.build_context()

    memory.set_status("paused")
    decision = interrupt({
        "type": "human_approval",
        "message": "Please review the generated code and choose an action.",
        "actions": ["approved", "rejected", "modify"],
        "code": state.get("code", ""),
        "review": state.get("review", {}),
    })

    action = decision.get("action", "approved")
    feedback = decision.get("feedback", "")

    memory.add_message("human", f"{action}: {feedback}", agent="human")
    memory.set_status("approved" if action == "approved" else "rejected")

    label = {"approved": "APPROVED", "rejected": "REJECTED", "modify": "MODIFY"}.get(action, action)

    return {
        "approval_status": action,
        "human_feedback": feedback,
        "messages": [
            AIMessage(content=f"[Human] {label} | feedback: {feedback or '(none)'}")
        ],
    }
