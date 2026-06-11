"""Agent 执行管道 — 实时逐步刷新，类似 Cursor 的步骤展示。"""

from __future__ import annotations

import streamlit as st

AGENTS = [
    {"key": "planner",       "label": "📋 规划器",     "desc": "分析需求，生成方案"},
    {"key": "code_agent",    "label": "💻 代码生成",   "desc": "根据方案编写代码"},
    {"key": "tool_node",     "label": "🔧 工具执行",   "desc": "读写文件、运行测试"},
    {"key": "reviewer",      "label": "🔍 代码审查",   "desc": "自动质量检查"},
    {"key": "human_approval","label": "👤 人工确认",   "desc": "等待审核"},
]

ICONS = {"pending": "○", "running": "◌", "complete": "●", "error": "✕"}
COLORS = {"pending": "#888", "running": "#FF9800", "complete": "#4CAF50", "error": "#F44336"}


def render_agent_pipeline() -> None:
    """渲染 5 步执行管道，动态刷新状态。"""
    steps = st.session_state.get("agent_steps", [])
    status_map = {s["agent"]: s["status"] for s in steps}
    output_map = {s["agent"]: s.get("output", "") for s in steps}

    for agent in AGENTS:
        key = agent["key"]
        status = status_map.get(key, "pending")
        icon = ICONS.get(status, "○")
        color = COLORS.get(status, "#888")
        label_html = f"<span style='color:{color};font-weight:bold'>{icon}</span> {agent['label']}"

        if status == "running":
            with st.status(label_html, expanded=True) as ctx:
                st.caption(f"⏳ {agent['desc']}...")
        elif status == "complete":
            with st.expander(label_html, expanded=(key == "reviewer")):
                st.caption(f"✅ {agent['desc']} — 完成")
                out = output_map.get(key)
                if out:
                    st.markdown(out[:2000])
        elif status == "error":
            st.error(f"{icon} {agent['label']} — 出错")
        else:
            st.caption(f"{icon} {agent['label']} — {agent['desc']}")


def update_agent_status(agent: str, status: str, output: str = "") -> None:
    """流式回调 — 更新指定 Agent 的状态。"""
    from frontend.utils.session import set_agent_step
    set_agent_step(agent, status, output)
