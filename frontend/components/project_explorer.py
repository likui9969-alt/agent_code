"""项目浏览器 — Cursor 风格文件树 + 新建/删除/刷新 + 最近项目。"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from frontend.services.file_manager import get_file_manager
from frontend.services.settings_store import get_settings_store


# Maximum entries rendered per directory node to keep the UI responsive.
_MAX_CHILDREN_PER_NODE = 100


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
                _open_project(path)

    # ── 最近项目快捷入口 ──
    recents = st.session_state.get("recent_projects", [])
    if recents:
        with st.expander("最近项目", expanded=False):
            for rp in recents[:5]:
                name = os.path.basename(rp)
                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button(f"📁 {name}", key=f"recent_{rp}", use_container_width=True):
                        _open_project(rp)
                with c2:
                    if st.button("✕", key=f"del_recent_{rp}", use_container_width=True, help="从历史移除"):
                        get_settings_store().remove_recent_project(rp)
                        st.session_state["recent_projects"] = get_settings_store().get("recent_projects", [])
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
    _render_tree_node(tree, fm)


def _open_project(path: str) -> None:
    """Open project, persist recent, and rerun."""
    from frontend.services.file_manager import get_file_manager
    try:
        resolved = str(Path(path).resolve())
        get_file_manager().open_project(path)
        st.session_state["project_path"] = resolved
        get_settings_store().add_recent_project(resolved)
        st.session_state["recent_projects"] = get_settings_store().get("recent_projects", [])
        st.success(f"已打开: {os.path.basename(path)}")
        st.rerun()
    except Exception as e:
        st.error(str(e))


def _sort_nodes(children: list[dict]) -> list[dict]:
    """Directories first, then files, both sorted by name."""
    dirs = [c for c in children if c.get("type") == "directory"]
    files = [c for c in children if c.get("type") == "file"]
    return sorted(dirs, key=lambda c: c.get("name", "").lower()) + \
           sorted(files, key=lambda c: c.get("name", "").lower())


def _indent(level: int) -> str:
    """Return a Unicode non-breaking-space indent string."""
    return "\u00A0" * (level * 3)


def _render_tree_node(node: dict, fm, level: int = 0) -> None:
    """Render a single tree node using native Streamlit expanders for folders."""
    name = node.get("name", "")
    is_dir = node.get("type") == "directory"
    children = node.get("children", [])
    node_path = node.get("path", name)

    if not is_dir:
        _render_file_row(name, node_path, fm, level)
        return

    # Root directory is rendered flat (no expander wrapper).
    if node_path == "." or node_path == "":
        for child in _sort_nodes(children):
            _render_tree_node(child, fm, level)
        return

    # Folder: use a native expander. Its open/closed state is managed by Streamlit.
    # Children are loaded lazily only when the expander is open.
    expander_label = f"{_indent(level)}📁 {name}"
    with st.expander(expander_label, expanded=False):
        sub = fm.scan_subdir(node_path)
        sub_children = sub.get("children", [])
        if len(sub_children) > _MAX_CHILDREN_PER_NODE:
            st.caption(f"目录条目过多，仅显示前 {_MAX_CHILDREN_PER_NODE} 项（共 {len(sub_children)} 项）")
        for child in _sort_nodes(sub_children[:_MAX_CHILDREN_PER_NODE]):
            _render_tree_node(child, fm, level + 1)


def _render_file_row(name: str, file_path: str, fm, level: int) -> None:
    """Render one file row with an open button and a delete button."""
    is_active = st.session_state.get("active_file") == file_path
    btn_type = "primary" if is_active else "secondary"
    cols = st.columns([6, 1])
    with cols[0]:
        if st.button(
            f"{_indent(level)}📄 {name}",
            key=f"file_{file_path}",
            use_container_width=True,
            type=btn_type,
            help=file_path,
        ):
            _open_file(fm, file_path)
    with cols[1]:
        if st.button("🗑", key=f"del_{file_path}", help="删除", use_container_width=True):
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
