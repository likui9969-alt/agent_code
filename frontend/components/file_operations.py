"""文件操作 — AI 生成代码 Apply + Diff + 自动打开到编辑器。"""

from __future__ import annotations

import difflib

import streamlit as st

from frontend.services.file_manager import get_file_manager


def render_apply_code_panel(code: str) -> None:
    """AI 代码应用面板 — 选择路径 → 预览 Diff → 确认写入 → 自动打开文件。"""
    if not code:
        return

    fm = get_file_manager()
    if not fm.is_open():
        return

    st.divider()
    st.subheader("📁 应用到项目")

    file_path = st.text_input("目标文件路径", value="output.py",
                              key="apply_path", placeholder="src/module.py")

    exists = fm.exists(file_path)

    if exists:
        original = fm.read(file_path)
        st.warning(f"文件已存在: `{file_path}`")
        with st.expander("📊 查看差异", expanded=False):
            diff_lines = list(difflib.unified_diff(
                original.splitlines(keepends=True),
                code.splitlines(keepends=True),
                fromfile=f"当前/{file_path}",
                tofile=f"AI 生成/{file_path}",
            ))
            if diff_lines:
                st.code("".join(diff_lines), language="diff")
            else:
                st.caption("无差异")
    else:
        st.info(f"将创建新文件: `{file_path}`")

    c1, c2 = st.columns(2)
    with c1:
        label = "✅ 覆盖文件" if exists else "✅ 创建文件"
        if st.button(label, type="primary", use_container_width=True, key="btn_apply_code"):
            try:
                fm.write(file_path, code)
                # 自动打开到编辑器
                st.session_state.setdefault("open_files", {})
                st.session_state["open_files"][file_path] = code
                st.session_state["active_file"] = file_path
                st.session_state.setdefault("file_modified", {})
                st.session_state["file_modified"][file_path] = False
                st.success(f"已保存: `{file_path}` — 已在编辑器中打开")
            except Exception as e:
                st.error(f"写入失败: {e}")
    with c2:
        if st.button("取消", use_container_width=True, key="btn_cancel_apply"):
            st.rerun()
