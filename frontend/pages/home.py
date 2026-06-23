"""首页 — 卡片化 Welcome 风格：快捷卡片 + 最近项目 + 示例 Prompt。"""

from __future__ import annotations

import datetime
import os
import streamlit as st

from frontend.config import THEME
from frontend.services.history_store import get_history_store


def _card_html(icon: str, title: str, desc: str) -> str:
    return f"""
    <div style="
        background: {THEME['bg_card']};
        border: 1px solid {THEME['border']};
        border-radius: {THEME['radius']};
        padding: 1rem;
        height: 100%;
        cursor: pointer;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    " onmouseover="this.style.transform='translateY(-2px)';this.style.boxShadow='0 4px 12px rgba(0,0,0,0.06)';"
    onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='none';">
        <div style="font-size: 1.6rem; margin-bottom: 0.4rem;">{icon}</div>
        <div style="font-weight: 600; color: {THEME['text']}; margin-bottom: 0.3rem;">{title}</div>
        <div style="font-size: 0.85rem; color: {THEME['text_muted']};">{desc}</div>
    </div>
    """


def render_home() -> None:
    """渲染首页。"""
    st.title("🧠 AI Code Assistant")
    st.caption("智能代码生成、审查、重构 — 一站式 AI 编程助手")

    # ── 顶部操作：打开项目 / 新建对话 ──
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📂 打开项目", use_container_width=True, key="home_open_proj"):
            st.session_state["page"] = "chat"
            st.rerun()
    with c2:
        if st.button("💬 新建对话", use_container_width=True, key="home_new_chat"):
            from frontend.app import _cb_new_chat
            _cb_new_chat()

    # ── 快捷卡片 ──
    st.subheader("🚀 快速开始")
    quick = [
        ("📡", "FastAPI 接口", "创建完整 CRUD 接口，支持 GET/POST/PATCH/DELETE",
         "用 FastAPI 创建完整的 CRUD 接口，支持 GET/POST/PATCH/DELETE"),
        ("🧪", "Pytest 测试", "生成完整 pytest 用例，包含边界条件",
         "为以下代码生成完整的 pytest 测试用例，包含边界条件"),
        ("⚡", "优化代码", "优化性能与可读性，保持功能不变",
         "优化以下代码的性能和可读性，保持功能不变"),
        ("📖", "解释代码", "详细解释代码逻辑与设计决策",
         "详细解释以下代码的逻辑和设计决策"),
    ]
    c1, c2, c3, c4 = st.columns(4)
    for i, (icon, title, desc, prompt) in enumerate(quick):
        with [c1, c2, c3, c4][i]:
            st.markdown(_card_html(icon, title, desc), unsafe_allow_html=True)
            if st.button("使用", key=f"q_{i}", use_container_width=True):
                st.session_state["chat_input_prompt"] = prompt
                st.session_state["page"] = "chat"
                st.rerun()

    # ── 最近项目 ──
    st.markdown("---")
    st.subheader("📁 最近项目")
    recent = st.session_state.get("recent_projects", [])
    if recent:
        cols = st.columns(min(len(recent[:6]), 3))
        for i, proj in enumerate(recent[:6]):
            name = os.path.basename(proj)
            with cols[i % 3]:
                st.markdown(_card_html("📁", name, proj), unsafe_allow_html=True)
                if st.button("打开", key=f"rp_{i}", use_container_width=True):
                    from frontend.services.file_manager import get_file_manager
                    from frontend.services.settings_store import get_settings_store
                    try:
                        get_file_manager().open_project(proj)
                        get_settings_store().add_recent_project(proj)
                        st.session_state["page"] = "chat"
                        st.success(f"已打开: {name}")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    else:
        st.caption("暂无最近项目 — 在左侧打开一个文件夹开始使用")

    # ── 最近对话 ──
    st.markdown("---")
    st.subheader("💬 最近对话")
    store = get_history_store()
    chats = store.list_chats(limit=6)
    if chats:
        cols = st.columns(min(len(chats), 3))
        for i, chat in enumerate(chats):
            title = chat.get("title", "未命名")[:30]
            ts = chat.get("updated_at", 0)
            dt = datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
            with cols[i % 3]:
                st.markdown(_card_html("💬", title, dt or "最近对话"), unsafe_allow_html=True)
                if st.button("继续", key=f"rc_{i}", use_container_width=True):
                    st.session_state["active_chat_id"] = chat["id"]
                    st.session_state["messages"] = chat.get("messages", [])
                    st.session_state["current_code"] = chat.get("code", "")
                    st.session_state["thread_id"] = chat.get("thread_id", "")
                    st.session_state["page"] = "chat"
                    st.rerun()
    else:
        st.caption("暂无历史记录 — 去聊天页开始吧！")

    # ── 示例 Prompts ──
    st.markdown("---")
    st.subheader("💡 试试这些")
    examples = [
        "用 Python 写一个快速排序算法",
        "创建 FastAPI 用户登录注册接口",
        "写一个斐波那契数列生成器",
        "审查这段代码的安全性",
        "重构这个函数使其更 Pythonic",
        "为这个类生成完整的 docstring",
    ]
    c1, c2, c3 = st.columns(3)
    for i, ex in enumerate(examples):
        with [c1, c2, c3][i % 3]:
            if st.button(ex, key=f"ex_{i}", use_container_width=True):
                st.session_state["chat_input_prompt"] = ex
                st.session_state["page"] = "chat"
                st.rerun()
