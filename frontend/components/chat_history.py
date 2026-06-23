"""对话历史 — 新建/删除/重命名/搜索/恢复。"""

from __future__ import annotations

import streamlit as st

from frontend.services.history_store import get_history_store


def render_chat_history(on_select, on_new, on_delete, on_rename) -> None:
    """渲染聊天历史列表。"""
    store = get_history_store()

    # ── 新建 + 搜索 ──
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("➕ 新建", use_container_width=True, key="new_chat_btn"):
            on_new()
            st.rerun()
    with c2:
        search = st.text_input("搜索", placeholder="搜索对话...",
                               key="search_hist", label_visibility="collapsed")

    # ── 列表 ──
    chats = store.list_chats()
    if search:
        chats = [c for c in chats if search.lower() in c.get("title", "").lower()]

    if not chats:
        st.caption("暂无历史记录")
        return

    for chat in chats[:30]:
        cid = chat["id"]
        title = chat.get("title", "新建对话")[:26]
        active = cid == st.session_state.get("active_chat_id")

        # Compact history item with inline actions
        container = st.container(border=active)
        with container:
            c1, c2 = st.columns([5, 1])
            with c1:
                label = f"▸ {title}" if active else f"  {title}"
                btn_type = "primary" if active else "secondary"
                if st.button(
                    label,
                    key=f"h_{cid}",
                    use_container_width=True,
                    type=btn_type,
                    help=title,
                ):
                    on_select(cid)
                    st.rerun()
            with c2:
                a1, a2 = st.columns(2)
                with a1:
                    if st.button("✎", key=f"rn_{cid}", help="重命名", use_container_width=True):
                        st.session_state["_rename_id"] = cid
                        st.rerun()
                with a2:
                    if st.button("✕", key=f"dl_{cid}", help="删除", use_container_width=True):
                        on_delete(cid)
                        st.rerun()

    # ── 重命名 ──
    rid = st.session_state.get("_rename_id")
    if rid:
        chat = store.get_chat(rid)
        old = chat["title"] if chat else ""
        new_name = st.text_input("新名称", value=old, key=f"rn_input_{rid}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认", key=f"rn_ok_{rid}") and new_name:
                on_rename(rid, new_name)
                st.session_state.pop("_rename_id", None)
                st.rerun()
        with c2:
            if st.button("取消", key=f"rn_cancel_{rid}"):
                st.session_state.pop("_rename_id", None)
                st.rerun()
