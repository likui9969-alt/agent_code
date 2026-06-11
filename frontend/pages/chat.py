"""聊天页 — 管道 + 审查 + 编辑器 + 代码 + Apply + 对话。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from frontend.components.agent_status import render_agent_pipeline, update_agent_status
from frontend.components.chat_window import render_chat_input, render_messages
from frontend.components.code_viewer import render_code_block, render_plan, render_tool_results
from frontend.components.editor_tabs import render_editor_tabs
from frontend.components.file_operations import render_apply_code_panel
from frontend.components.review_panel import render_review_panel, show_paused_banner
from frontend.config import API_BASE_URL
from frontend.services.api_client import APIClient
from frontend.services.file_manager import get_file_manager
from frontend.services.history_store import get_history_store
from frontend.utils.session import add_message

store = get_history_store()


def _api() -> APIClient:
    return APIClient(st.session_state.get("api_base_url", API_BASE_URL))


def render_chat() -> None:
    st.title("🧠 AI 代码助手")
    st.caption("规划 → 编码 → 工具 → 审查 → 人工确认")

    # ── 管道 ──
    with st.expander("🔧 执行管道", expanded=True):
        render_agent_pipeline()

    # ── 审批 ──
    if st.session_state.get("paused") and st.session_state.get("review"):
        show_paused_banner(st.session_state.get("thread_id", ""))
        render_review_panel(st.session_state.get("review", {}), on_decision=_handle_decision)

    # ── 编辑器 (有文件时自动展开) ──
    has_files = bool(st.session_state.get("open_files"))
    with st.expander("📝 编辑器", expanded=has_files):
        render_editor_tabs()

    # ── 生成代码 ──
    code = st.session_state.get("current_code", "")
    if code:
        st.divider()
        st.subheader("💻 生成代码")
        render_code_block(code)
        render_apply_code_panel(code)

    # ── Plan ──
    for step in st.session_state.get("agent_steps", []):
        if step["agent"] == "planner" and step.get("output"):
            render_plan(step["output"])
            break

    # ── 工具结果 ──
    tr = st.session_state.get("tool_results", [])
    if tr:
        render_tool_results(tr)

    # ── 对话 ──
    st.divider()
    st.subheader("💬 对话")
    render_messages()

    # ── 输入 ──
    if st.session_state.get("paused"):
        st.info("⏸️ 请先审核上面的代码审查结果")
    else:
        render_chat_input(on_send=_handle_send)


# ═══════════════════════════════════════════════════════════════════════════════
# 回调
# ═══════════════════════════════════════════════════════════════════════════════

def _project_path() -> str | None:
    fm = get_file_manager()
    path = fm.get_project_path()
    return path if path else None


def _sync_written_files() -> None:
    """After agent write_file, load real disk content into the editor."""
    fm = get_file_manager()
    if not fm.is_open():
        return
    versions = st.session_state.setdefault("editor_version", {})
    for r in st.session_state.get("tool_results", []):
        if r.get("tool_name") != "write_file" or not r.get("success"):
            continue
        rel = (r.get("metadata") or {}).get("path") or (r.get("arguments") or {}).get("path")
        if not rel:
            continue
        try:
            content = fm.read(rel)
            st.session_state.setdefault("open_files", {})
            st.session_state["open_files"][rel] = content
            st.session_state["active_file"] = rel
            st.session_state.setdefault("file_modified", {})
            st.session_state["file_modified"][rel] = False
            versions[rel] = versions.get(rel, 0) + 1
        except Exception:
            pass


def _persist_chat(cid: str) -> None:
    """Save full chat session state to local history."""
    store.update_chat(
        cid,
        messages=st.session_state.get("messages", []),
        code=st.session_state.get("current_code", ""),
        thread_id=st.session_state.get("thread_id", ""),
        review=st.session_state.get("review"),
        paused=st.session_state.get("paused", False),
        agent_steps=st.session_state.get("agent_steps", []),
        tool_results=st.session_state.get("tool_results", []),
        target_file=st.session_state.get("target_file", ""),
    )


def _handle_send(user_input: str, thread_id: str | None) -> None:
    st.session_state["streaming"] = True
    st.session_state["paused"] = False
    st.session_state["agent_steps"] = []
    st.session_state["review"] = None
    st.session_state["tool_results"] = []
    for k in ["planner", "code_agent", "tool_node", "reviewer", "human_approval"]:
        update_agent_status(k, "pending")

    cid = st.session_state.get("active_chat_id")
    if not cid:
        cid = store.create_chat(user_input[:30])
        st.session_state["active_chat_id"] = cid

    try:
        for event in _api().post_chat_stream(user_input, thread_id, _project_path()):
            _on_event(event)
    except Exception as exc:
        st.error(f"连接错误: {exc}")
        st.session_state["streaming"] = False
        return

    _sync_state()
    _sync_written_files()
    _persist_chat(cid)
    st.session_state["streaming"] = False
    st.rerun()


def _handle_decision(action: str, feedback: str) -> None:
    tid = st.session_state.get("thread_id")
    if not tid:
        return
    st.session_state["streaming"] = True
    update_agent_status("human_approval", "running")
    try:
        for event in _api().post_resume_stream(tid, action, feedback, _project_path()):
            _on_event(event)
    except Exception as exc:
        st.error(f"恢复错误: {exc}")
        st.session_state["streaming"] = False
        return
    _sync_state()
    _sync_written_files()
    cid = st.session_state.get("active_chat_id")
    if cid:
        _persist_chat(cid)
    st.session_state["review_decision_mode"] = None
    st.session_state["streaming"] = False
    st.rerun()


def _sync_state() -> None:
    tid = st.session_state.get("thread_id")
    if not tid:
        return
    try:
        s = _api().get_state(tid)
        st.session_state["current_code"] = s.get("code", "")
        st.session_state["review"] = s.get("review")
        st.session_state["paused"] = s.get("status") == "paused"
        st.session_state["tool_results"] = s.get("tool_results", [])
        if s.get("target_file"):
            st.session_state["target_file"] = s["target_file"]
        for msg in s.get("messages", []):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "human" and content and not any(
                m.get("content") == content for m in st.session_state.get("messages", [])
            ):
                add_message("user", content)
            elif role in ("ai", "assistant") and content:
                agent = ""
                if content.startswith("[Planner]"):
                    agent = "planner"
                    content = content[len("[Planner]"):].strip()
                    update_agent_status("planner", "complete", content)
                elif content.startswith("[CodeAgent"):
                    agent = "code_agent"
                    update_agent_status("code_agent", "complete")
                elif content.startswith("[Reviewer]"):
                    agent = "reviewer"
                    update_agent_status("reviewer", "complete")
                if agent and not any(
                    m.get("content") == content[:1500] for m in st.session_state.get("messages", [])
                ):
                    add_message("ai", content[:1500], agent=agent)
        if st.session_state.get("paused"):
            update_agent_status("human_approval", "pending")
    except Exception:
        pass


def _on_event(event: dict) -> None:
    etype = event.get("_event", event.get("event", ""))
    if etype == "start":
        st.session_state["thread_id"] = event.get("thread_id")
    elif etype == "node_done":
        node = event.get("node", "")
        out = event.get("output", {})
        if node == "planner":
            update_agent_status("planner", "complete", out.get("plan", ""))
            add_message("ai", out.get("plan", ""), agent="planner")
        elif node == "code_agent":
            st.session_state["current_code"] = out.get("code", "")
            if out.get("target_file"):
                st.session_state["target_file"] = out["target_file"]
            update_agent_status("code_agent", "complete")
            add_message("ai", out.get("code", "")[:1500], agent="code_agent")
        elif node == "tool_node":
            update_agent_status("tool_node", "complete")
            if out.get("tool_results"):
                st.session_state["tool_results"] = out["tool_results"]
                _sync_written_files()
        elif node == "reviewer":
            rev = out.get("review", {})
            st.session_state["review"] = rev
            msg = "通过" if rev.get("passed") else f"{len(rev.get('issues', []))} 个问题"
            update_agent_status("reviewer", "complete", msg)
        elif node == "human_approval":
            update_agent_status("human_approval", "pending")
    elif etype == "tool_call":
        update_agent_status("tool_node", "running", event.get("tool_name", ""))
    elif etype == "interrupt":
        st.session_state["paused"] = True
        update_agent_status("human_approval", "pending")
    elif etype == "done":
        for k in ["planner", "code_agent", "tool_node", "reviewer"]:
            cur = next((s for s in st.session_state.get("agent_steps", [])
                        if s["agent"] == k), None)
            if cur and cur["status"] == "running":
                update_agent_status(k, "complete")
        st.session_state["paused"] = False
    elif etype == "error":
        st.toast(f"错误: {event.get('message', '?')}")
