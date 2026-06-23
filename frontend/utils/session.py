"""Streamlit session-state helpers."""

from __future__ import annotations

import streamlit as st

from frontend.services.settings_store import get_settings_store


def init_session() -> None:
    """Ensure all required session-state keys exist (called once at startup)."""
    settings = get_settings_store().all()
    defaults = {
        "messages": [],             # list of {"role":str, "agent":str, "content":str}
        "agent_steps": [],          # list of {"agent":str, "status":str, "output":str}
        "current_code": "",         # latest generated code
        "review": None,             # {"passed":bool, "issues":[...]}
        "thread_id": None,          # current conversation thread
        "paused": False,            # waiting for human input?
        "history": [],              # [{"id":str, "title":str, "ts":float}, ...]
        "streaming": False,         # currently receiving SSE?
        # ── persisted settings ──
        "lang": settings.get("lang", "zh"),
        "theme_idx": settings.get("theme_idx", 0),
        "settings_model_idx": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-plus-latest"].index(
            settings.get("model", "qwen-plus")
        ),
        "api_key": settings.get("api_key", ""),
        "api_base_url": settings.get("api_base_url", "http://localhost:8000"),
        "auto_save": settings.get("auto_save", True),
        "recent_projects": settings.get("recent_projects", []),
        "saved_settings": settings,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_session() -> None:
    """Clear the current session (start new conversation)."""
    st.session_state["messages"] = []
    st.session_state["agent_steps"] = []
    st.session_state["current_code"] = ""
    st.session_state["review"] = None
    st.session_state["thread_id"] = None
    st.session_state["paused"] = False
    st.session_state["streaming"] = False


def add_message(role: str, content: str, agent: str = "") -> None:
    st.session_state["messages"].append({
        "role": role,
        "agent": agent,
        "content": content,
    })


def set_agent_step(agent: str, status: str, output: str = "") -> None:
    """Update or append an agent execution step."""
    for step in st.session_state["agent_steps"]:
        if step["agent"] == agent:
            step["status"] = status
            if output:
                step["output"] = output
            return
    st.session_state["agent_steps"].append({
        "agent": agent, "status": status, "output": output,
    })


def persist_setting(key: str, value: any) -> None:
    """Persist a single setting to disk and update session_state."""
    st.session_state[key] = value
    get_settings_store().set(key, value)


def persist_settings(**kwargs: any) -> None:
    """Persist multiple settings to disk and update session_state."""
    st.session_state.update(kwargs)
    get_settings_store().update(**kwargs)
