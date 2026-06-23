"""编辑器标签页 — 显示实际代码 + Diff + 保存。"""

from __future__ import annotations

import difflib
from pathlib import Path

import streamlit as st

from frontend.services.file_manager import get_file_manager


def render_editor_tabs() -> None:
    """多文件标签 + 编辑器 + Diff 对比。"""
    open_files: dict = st.session_state.get("open_files", {})
    active_file: str = st.session_state.get("active_file", "")
    modified: dict = st.session_state.get("file_modified", {})

    if not open_files:
        st.caption("点击左侧文件树中的 📄 文件即可打开")
        return

    # ── 标签栏 ──
    names = list(open_files.keys())
    tab_cols = st.columns([1] * min(len(names), 5) + [0.2])
    for i, fp in enumerate(names[:5]):
        with tab_cols[i]:
            label = Path(fp).name
            m = "•" if modified.get(fp) else ""
            t = "primary" if fp == active_file else "secondary"
            display = f"{label} {m}" if m else label
            if st.button(display, key=f"tab_{fp}", use_container_width=True, type=t):
                st.session_state["active_file"] = fp
                st.rerun()
    with tab_cols[-1]:
        if st.button("✕", key="cls_all", use_container_width=True, help="关闭全部"):
            st.session_state["open_files"] = {}
            st.session_state["active_file"] = ""
            st.rerun()

    if len(names) > 5:
        st.caption(f"还有 {len(names) - 5} 个打开的文件未显示")

    # ── 活跃文件 ──
    if not active_file or active_file not in open_files:
        st.caption("选择一个标签查看代码")
        return

    content = open_files.get(active_file, "")
    fm = get_file_manager()

    # ── Diff 模式 ──
    show_diff = st.checkbox("对比磁盘文件", key=f"diff_ck_{active_file}")
    if show_diff and fm.is_open() and fm.exists(active_file):
        disk = fm.read(active_file)
        if disk != content:
            diff_lines = list(difflib.unified_diff(
                disk.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"磁盘/{active_file}",
                tofile=f"编辑器/{active_file}",
            ))
            if diff_lines:
                st.code("".join(diff_lines), language="diff")
            else:
                st.caption("无差异")
        else:
            st.success("编辑器内容与磁盘文件一致")

    # ── 代码编辑器 ──
    version = st.session_state.get("editor_version", {}).get(active_file, 0)
    new_content = st.text_area(
        "代码内容",
        value=content,
        height=350,
        key=f"editor_area_{active_file}_{version}",
        label_visibility="collapsed",
    )

    if new_content != content:
        st.session_state["open_files"][active_file] = new_content
        st.session_state["file_modified"][active_file] = True

    # ── 操作栏 ──
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if st.button("💾 保存到磁盘", key=f"save_btn_{active_file}",
                     type="primary", use_container_width=True):
            try:
                fm.write(active_file, new_content)
                st.session_state["file_modified"][active_file] = False
                st.success(f"已保存: {active_file}")
            except Exception as e:
                st.error(f"保存失败: {e}")
    with c2:
        lines = new_content.count("\n") + 1
        st.metric("行 / 字符", f"{lines}", f"{len(new_content)} 字符", help="行数 / 字符数")
    with c3:
        if st.button("✕ 关闭", key=f"cls_btn_{active_file}", use_container_width=True):
            st.session_state["open_files"].pop(active_file, None)
            st.session_state["file_modified"].pop(active_file, None)
            remaining = list(st.session_state["open_files"].keys())
            st.session_state["active_file"] = remaining[0] if remaining else ""
            st.rerun()
