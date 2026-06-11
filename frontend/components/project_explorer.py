"""Cursor 风格项目浏览器 — 真正的目录树 + 展开折叠 + 文件操作。"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from frontend.services.file_manager import get_file_manager


def render_project_explorer() -> None:
    """侧边栏：打开项目 + 文件树 + 新建/删除/刷新。"""
    fm = get_file_manager()

    # ── 打开项目行 ──
    c1, c2 = st.columns([5, 1])
    with c1:
        path = st.text_input(
            "项目路径", value=fm.get_project_path() or "",
            placeholder=os.getcwd(), key="proj_path",
            label_visibility="collapsed",
        )
    with c2:
        if st.button("📂", help="打开项目", key="btn_open_proj", use_container_width=True):
            if path and os.path.isdir(path):
                fm.open_project(path)
                st.session_state["project_path"] = str(Path(path).resolve())
                st.rerun()

    if not fm.is_open():
        st.caption("点击 📂 打开项目文件夹")
        return

    # ── 操作栏 ──
    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        if st.button("🆕", help="新建文件", key="btn_newf", use_container_width=True):
            st.session_state["_new_file"] = True
    with c2:
        if st.button("🔄", help="刷新", key="btn_refreshf", use_container_width=True):
            st.rerun()
    with c3:
        st.caption(f"📁 {fm.get_project_name()}")

    # ── 新建文件弹窗 ──
    if st.session_state.get("_new_file"):
        new_name = st.text_input("文件名", placeholder="src/new.py", key="new_fname")
        ca, cb = st.columns(2)
        with ca:
            if st.button("创建", key="create_f") and new_name:
                try:
                    fm.create_file(new_name)
                    st.session_state["_new_file"] = False
                    st.success("已创建")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with cb:
            if st.button("取消", key="cancel_f"):
                st.session_state["_new_file"] = False
                st.rerun()

    # ── 文件树 ──
    tree = fm.scan()
    _render_node(tree, fm, "")


def _render_node(node: dict, fm, prefix: str) -> None:
    """递归渲染树节点 — 文件夹可折叠，文件可点击打开/删除。"""
    name = node.get("name", "")
    is_dir = node.get("type") == "directory"
    children = node.get("children", [])
    node_path = node.get("path", name)

    if is_dir:
        key = f"tree_dir_{node_path}"
        expanded = st.session_state.get(key, False)
        icon = "📂" if expanded else "📁"
        label = f"{prefix}{icon} {name}"
        if st.button(label, key=f"btn_{node_path}", use_container_width=True):
            st.session_state[key] = not expanded
            st.rerun()
        if expanded:
            for child in children:
                _render_node(child, fm, prefix + "  ")
    else:
        file_path = node.get("path", name)
        c1, c2 = st.columns([8, 1])
        with c1:
            label = f"{prefix}📄 {name}"
            is_active = st.session_state.get("active_file") == file_path
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"file_{file_path}", use_container_width=True, type=btn_type):
                _open_file(fm, file_path)
        with c2:
            if st.button("🗑", key=f"del_{file_path}", help="删除"):
                fm.delete_file(file_path)
                st.success("已删除")
                st.rerun()


def _open_file(fm, path: str) -> None:
    """打开文件到编辑器标签页。"""
    try:
        content = fm.read(path)
        st.session_state.setdefault("open_files", {})
        st.session_state["open_files"][path] = content
        st.session_state["active_file"] = path
        st.session_state.setdefault("file_modified", {})
        st.session_state["file_modified"][path] = False
    except Exception as e:
        st.error(str(e))
