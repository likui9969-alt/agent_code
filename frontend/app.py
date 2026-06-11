"""AI Code Assistant — Streamlit 单入口应用。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from frontend.config import PAGE_TITLE, PAGE_ICON, LAYOUT
from frontend.i18n import t
from frontend.utils.session import init_session
from frontend.services.history_store import get_history_store
from frontend.components.project_explorer import render_project_explorer
from frontend.components.chat_history import render_chat_history
from frontend.pages.home import render_home
from frontend.pages.chat import render_chat
from frontend.pages.settings import render_settings

# ── 必须第一个 Streamlit 命令 ──
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)
init_session()

# ── 路由默认值 ──
if "page" not in st.session_state:
    st.session_state["page"] = "home"

store = get_history_store()


# ═══════════════════════════════════════════════════════════════════════════════
# 侧边栏回调 (纯数据操作, 不调用 st.rerun)
# ═══════════════════════════════════════════════════════════════════════════════

def _cb_new_chat():
    cid = store.create_chat()
    st.session_state["active_chat_id"] = cid
    st.session_state["messages"] = []
    st.session_state["current_code"] = ""
    st.session_state["thread_id"] = ""
    st.session_state["agent_steps"] = []
    st.session_state["review"] = None
    st.session_state["paused"] = False
    st.session_state["tool_results"] = []
    st.session_state["page"] = "chat"

def _cb_select_chat(cid):
    chat = store.get_chat(cid)
    if chat:
        st.session_state["active_chat_id"] = cid
        st.session_state["messages"] = chat.get("messages", [])
        st.session_state["current_code"] = chat.get("code", "")
        st.session_state["thread_id"] = chat.get("thread_id", "")
        st.session_state["review"] = chat.get("review")
        st.session_state["paused"] = chat.get("paused", False)
        st.session_state["agent_steps"] = chat.get("agent_steps", [])
        st.session_state["tool_results"] = chat.get("tool_results", [])
        st.session_state["target_file"] = chat.get("target_file", "")
        st.session_state["review_decision_mode"] = None
        st.session_state["page"] = "chat"

def _cb_delete_chat(cid):
    store.delete_chat(cid)
    if st.session_state.get("active_chat_id") == cid:
        st.session_state["active_chat_id"] = ""

def _cb_rename_chat(cid, name):
    store.rename_chat(cid, name)

def _cb_nav(page_name):
    st.session_state["page"] = page_name


# ═══════════════════════════════════════════════════════════════════════════════
# 侧边栏 (三区段)
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🧠 AI Code Assistant")

    # ── 区段 1: 项目 ──
    st.subheader(t("project"))
    render_project_explorer()

    st.divider()

    # ── 区段 2: 历史记录 ──
    st.subheader(t("chat_history"))
    render_chat_history(
        on_select=_cb_select_chat,
        on_new=_cb_new_chat,
        on_delete=_cb_delete_chat,
        on_rename=_cb_rename_chat,
    )

    st.divider()

    # ── 区段 3: 导航 ──
    pg = st.session_state.get("page", "home")
    nav_items = [
        ("home", "🏠 首页"),
        ("chat", "💬 聊天"),
        ("settings", "⚙️ 设置"),
    ]
    for key, label in nav_items:
        active = pg == key
        if st.button(f"{'▸ ' if active else '  '}{label}",
                     use_container_width=True,
                     type="primary" if active else "secondary",
                     key=f"nav_{key}"):
            _cb_nav(key)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# 主区域 — 路由到页面
# ═══════════════════════════════════════════════════════════════════════════════

page = st.session_state.get("page", "home")

if page == "home":
    render_home()
elif page == "chat":
    render_chat()
elif page == "settings":
    render_settings()
