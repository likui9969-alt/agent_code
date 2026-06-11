"""Code viewer — syntax highlighting, Markdown, copy-to-clipboard."""

from __future__ import annotations

import streamlit as st


def render_code_block(code: str, language: str = "python") -> None:
    """Render code with syntax highlighting and a copy button.

    Args:
        code: Source code string.
        language: Programming language for syntax highlighting.
    """
    if not code:
        return

    col_code, col_btn = st.columns([10, 1])
    with col_code:
        st.code(code, language=language, line_numbers=True)
    with col_btn:
        st.button("📋", key=f"copy_{hash(code) % 10000}", help="Copy code",
                   on_click=_copy_to_clipboard, args=(code,),
                   use_container_width=True)


def render_markdown(content: str) -> None:
    """Render Markdown content (plans, review results, etc.)."""
    if content:
        st.markdown(content)


def render_plan(plan: str) -> None:
    """Render a Planner output block with nice formatting."""
    if plan:
        with st.expander("📋 Implementation Plan", expanded=True):
            st.markdown(plan)


def render_tool_results(tool_results: list[dict]) -> None:
    """Render tool execution results as a compact table."""
    if not tool_results:
        return
    with st.expander("🔧 Tool Execution Results", expanded=False):
        for r in tool_results:
            name = r.get("tool_name", "?")
            ok = r.get("success", False)
            out = str(r.get("output", ""))[:200]
            icon = "✅" if ok else "❌"
            st.caption(f"{icon} **{name}** — {out}")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard via Streamlit + JS interop."""
    try:
        import pyperclip
        pyperclip.copy(text)
        st.toast("Copied!", icon="📋")
    except Exception:
        st.info("Code copied (fallback)")
