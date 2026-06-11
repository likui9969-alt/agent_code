"""聊天窗口 — 中文输入框 + 消息气泡 + Markdown + 代码高亮。"""

from __future__ import annotations

import streamlit as st

from frontend.utils.session import add_message


def render_chat_input(on_send) -> None:
    """底部输入框 — 全中文。"""
    user_input = st.chat_input("请输入你的需求，例如：用 Python 写一个快速排序...")
    if user_input:
        add_message("user", user_input)
        on_send(user_input, st.session_state.get("thread_id"))


def render_messages() -> None:
    """渲染所有对话气泡。"""
    for msg in st.session_state.get("messages", []):
        role = msg.get("role", "")
        agent = msg.get("agent", "")
        content = msg.get("content", "")

        labels = {
            "planner": "📋 规划器", "code_agent": "💻 代码生成",
            "reviewer": "🔍 审查", "human": "👤 用户决策",
            "tool_node": "🔧 工具",
        }

        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(content)
        else:
            avatar = "🤖" if not agent else None
            with st.chat_message("assistant", avatar=avatar):
                if agent and agent in labels:
                    st.caption(labels[agent])
                # Markdown 渲染 (支持代码块)
                st.markdown(content[:4000])


def render_input_box(on_send) -> None:
    """备用输入框 — 当 chat_input 不可用时。"""
    c1, c2 = st.columns([8, 1])
    with c1:
        text = st.text_area("输入", placeholder="请输入你的需求...",
                            key="alt_input", label_visibility="collapsed", height=68)
    with c2:
        if st.button("发送", key="send_btn", use_container_width=True, type="primary"):
            if text.strip():
                add_message("user", text)
                on_send(text, st.session_state.get("thread_id"))
                st.session_state["alt_input"] = ""
                st.rerun()
