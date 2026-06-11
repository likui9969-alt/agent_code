"""首页 — Cursor Welcome 风格：快捷按钮 + 最近项目 + 示例 Prompt。"""

from __future__ import annotations

import datetime
import os
import streamlit as st

from frontend.services.history_store import get_history_store


def render_home() -> None:
    """渲染首页。"""
    st.title("🧠 欢迎使用 AI Code Assistant")
    st.caption("智能代码生成、审查、重构 — 一站式 AI 编程助手")

    # ── 四个快捷按钮 ──
    st.subheader("🚀 快速开始")
    c1, c2, c3, c4 = st.columns(4)
    quick = [
        ("📡 FastAPI 接口", "用 FastAPI 创建完整的 CRUD 接口，支持 GET/POST/PATCH/DELETE"),
        ("🧪 Pytest 测试", "为以下代码生成完整的 pytest 测试用例，包含边界条件"),
        ("⚡ 优化代码", "优化以下代码的性能和可读性，保持功能不变"),
        ("📖 解释代码", "详细解释以下代码的逻辑和设计决策"),
    ]
    for i, (label, prompt) in enumerate(quick):
        with [c1, c2, c3, c4][i]:
            if st.button(label, key=f"q_{i}", use_container_width=True):
                st.session_state["chat_input_prompt"] = prompt
                st.session_state["page"] = "chat"
                st.rerun()

    st.divider()

    # ── 最近项目 ──
    st.subheader("📁 最近项目")
    recent = st.session_state.get("recent_projects", [os.getcwd()])
    cols = st.columns(3)
    for i, proj in enumerate(recent[-6:]):
        name = os.path.basename(proj)
        with cols[i % 3]:
            if st.button(f"📁 {name}", key=f"rp_{i}", use_container_width=True):
                from frontend.services.file_manager import get_file_manager
                try:
                    get_file_manager().open_project(proj)
                    st.session_state["page"] = "chat"
                    st.success(f"已打开: {name}")
                except Exception as e:
                    st.error(str(e))

    st.divider()

    # ── 最近对话 ──
    st.subheader("💬 最近对话")
    store = get_history_store()
    chats = store.list_chats(limit=6)
    if chats:
        cols = st.columns(3)
        for i, chat in enumerate(chats):
            title = chat.get("title", "未命名")[:30]
            ts = chat.get("updated_at", 0)
            dt = datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
            with cols[i % 3]:
                if st.button(f"💬 {title}\n{dt}", key=f"rc_{i}", use_container_width=True):
                    st.session_state["active_chat_id"] = chat["id"]
                    st.session_state["messages"] = chat.get("messages", [])
                    st.session_state["current_code"] = chat.get("code", "")
                    st.session_state["thread_id"] = chat.get("thread_id", "")
                    st.session_state["page"] = "chat"
                    st.rerun()
    else:
        st.caption("暂无历史记录 — 去聊天页开始吧！")

    st.divider()

    # ── 示例 Prompts ──
    st.subheader("💡 试试这些")
    examples = [
        "用 Python 写一个快速排序算法",
        "创建 FastAPI 用户登录注册接口",
        "写一个斐波那契数列生成器",
        "审查这段代码的安全性",
        "重构这个函数使其更 Pythonic",
        "为这个类生成完整的 docstring",
    ]
    cols = st.columns(3)
    for i, ex in enumerate(examples):
        with cols[i % 3]:
            if st.button(ex, key=f"ex_{i}", use_container_width=True):
                st.session_state["chat_input_prompt"] = ex
                st.session_state["page"] = "chat"
                st.rerun()
