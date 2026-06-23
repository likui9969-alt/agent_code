"""AI Code Assistant — Streamlit 单入口应用。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from frontend.config import PAGE_TITLE, PAGE_ICON, LAYOUT, THEME
from frontend.i18n import t
from frontend.utils.session import init_session
from frontend.services.history_store import get_history_store
from frontend.services.settings_store import get_settings_store
from frontend.components.project_explorer import render_project_explorer
from frontend.components.chat_history import render_chat_history
from frontend.pages.home import render_home
from frontend.pages.chat import render_chat
from frontend.pages.settings import render_settings

# ── 必须第一个 Streamlit 命令 ──
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)
init_session()


def _inject_global_styles() -> None:
    """Inject a minimal design-system CSS to unify the Streamlit UI."""
    is_dark = st.session_state.get("theme_idx", 0) == 1
    if is_dark:
        bg = "#0F172A"           # slate-900
        fg = "#F8FAFC"           # slate-50
        muted = "#94A3B8"        # slate-400
        card = "#1E293B"         # slate-800
        border = "#334155"       # slate-700
    else:
        bg = "#FFFFFF"
        fg = THEME["text"]
        muted = THEME["text_muted"]
        card = THEME["bg_card"]
        border = THEME["border"]

    css = f"""
    <style>
    /* ── Base ── */
    .stApp {{
        background-color: {bg};
    }}
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {fg} !important;
        font-weight: 600;
    }}
    p, div, span, label {{
        color: {fg};
    }}
    .stCaption {{
        color: {muted};
    }}

    /* ── Cards / Containers ── */
    .stAlert, div[data-testid="stExpander"], div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        border-radius: {THEME["radius"]};
        border: 1px solid {border};
        background-color: {card};
    }}

    /* ── Buttons ── */
    div.stButton > button:first-child {{
        border-radius: {THEME["radius"]};
        font-weight: 500;
        transition: all 0.15s ease;
    }}
    div.stButton > button:first-child:hover {{
        transform: translateY(-1px);
        box-shadow: 0 2px 6px rgba(0,0,0,0.12);
    }}
    div.stButton > button[kind="primary"] {{
        background-color: {THEME["primary"]};
        border-color: {THEME["primary"]};
        color: #fff;
    }}
    div.stButton > button[kind="primary"]:hover {{
        background-color: {THEME["primary_hover"]};
        border-color: {THEME["primary_hover"]};
    }}
    div.stButton > button[kind="secondary"] {{
        background-color: {card};
        border-color: {border};
        color: {fg};
    }}

    /* ── Chat input ── */
    div[data-testid="stChatInput"] > div {{
        border-radius: {THEME["radius"]};
        border: 1px solid {border};
        background-color: {card};
    }}

    /* ── Sidebar tidy ── */
    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1rem;
        background-color: {card};
    }}
    section[data-testid="stSidebar"] hr {{
        margin: 0.75rem 0;
        border-color: {border};
    }}

    /* ── Code blocks ── */
    div[data-testid="stCodeBlock"] pre {{
        border-radius: {THEME["radius"]};
        border: 1px solid {border};
    }}

    /* ── Metric cards ── */
    div[data-testid="stMetric"] {{
        background: {card};
        border: 1px solid {border};
        border-radius: {THEME["radius"]};
        padding: 0.5rem;
    }}
    div[data-testid="stMetric"] label {{
        color: {muted};
    }}

    /* ── Inputs ── */
    div[data-testid="stTextInput"] > div, div[data-testid="stTextArea"] > div {{
        border-radius: {THEME["radius"]};
        border-color: {border};
        background-color: {card};
    }}
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {{
        color: {fg};
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


_inject_global_styles()

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
