"""History sidebar — past conversations + new-chat button."""

from __future__ import annotations

import streamlit as st


def render_history_sidebar(on_select, on_new) -> None:
    """Render the history sidebar.

    Args:
        on_select:  Callback(thread_id) when a past conversation is clicked.
        on_new:     Callback() when the "New Chat" button is clicked.
    """
    with st.sidebar:
        st.header("📁 History")

        if st.button("➕ New Chat", use_container_width=True):
            on_new()
            st.rerun()

        st.divider()

        history = st.session_state.get("history", [])
        if not history:
            st.caption("(no conversations yet)")
        else:
            for entry in history:
                title = entry.get("title", "Untitled")[:40]
                tid = entry.get("id", "")
                active = tid == st.session_state.get("thread_id")
                prefix = "▸ " if active else "  "
                if st.button(
                    f"{prefix}{title}",
                    key=f"hist_{tid}",
                    use_container_width=True,
                    type="secondary" if not active else "primary",
                ):
                    on_select(tid)
                    st.rerun()
