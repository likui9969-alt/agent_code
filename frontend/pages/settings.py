"""设置页 — 模型 / API Key / 语言 / 主题 / 后端地址。"""

from __future__ import annotations

import streamlit as st

from frontend.config import API_BASE_URL
from frontend.i18n import t
from frontend.services.api_client import APIClient


def _api() -> APIClient:
    return APIClient(st.session_state.get("api_base_url", API_BASE_URL))


def _push_llm_settings(api_key: str | None = None, model: str | None = None) -> bool:
    """Send LLM credentials to the FastAPI backend."""
    try:
        result = _api().configure_llm(api_key=api_key, model=model)
        return result.get("configured", False)
    except Exception as exc:
        st.error(f"后端同步失败: {exc}")
        return False


def render_settings() -> None:
    """渲染设置页面内容。"""
    st.title(t("settings"))

    # ── 模型选择 ──
    st.subheader("🤖 模型配置")
    model = st.selectbox(
        "选择模型",
        options=["qwen-plus", "qwen-max", "qwen-turbo", "qwen-plus-latest"],
        index=st.session_state.get("settings_model_idx", 0),
    )
    if model:
        import os
        os.environ["QWEN_MODEL"] = model
        st.caption(f"当前: **{model}**")

    st.divider()

    # ── API Key ──
    st.subheader("🔑 API Key")
    current_key = st.session_state.get("api_key", "")
    if current_key:
        st.caption(f"已配置: `{current_key[:4]}...{current_key[-4:]}`")
    api_key = st.text_input(
        "输入 API Key", type="password",
        value=current_key, placeholder="sk-...",
    )
    if api_key and api_key != current_key:
        st.session_state["api_key"] = api_key
        if _push_llm_settings(api_key=api_key):
            st.success("已保存并同步到后端")
        else:
            st.warning("已本地保存，但后端未配置 Key")

    st.divider()

    # ── 语言 ──
    st.subheader("🌐 语言 / Language")
    lang = st.radio(
        "界面语言", options=["中文", "English"], horizontal=True,
        index=0 if st.session_state.get("lang", "zh") == "zh" else 1,
    )
    st.session_state["lang"] = "zh" if lang == "中文" else "en"

    st.divider()

    # ── 主题 ──
    st.subheader("🎨 主题")
    theme = st.radio(
        "颜色主题", options=["浅色", "暗色", "跟随系统"], horizontal=True,
        index=st.session_state.get("theme_idx", 0),
    )

    st.divider()

    # ── 后端地址 ──
    st.subheader("🔗 后端服务")
    backend = st.text_input(
        "API 地址",
        value=st.session_state.get("api_base_url", "http://localhost:8000"),
    )
    if backend:
        st.session_state["api_base_url"] = backend

    st.divider()

    # ── 自动保存 ──
    auto = st.toggle("自动保存对话", value=st.session_state.get("auto_save", True))
    st.session_state["auto_save"] = auto

    # ── 保存按钮 ──
    if st.button("💾 保存设置", type="primary", use_container_width=True):
        st.session_state["saved_settings"] = {
            "model": model, "lang": lang, "theme": theme,
            "backend": backend, "auto_save": auto,
        }
        key = st.session_state.get("api_key") or None
        if _push_llm_settings(api_key=key, model=model):
            st.success("✅ 设置已保存并同步到后端")
        else:
            st.success("✅ 设置已保存（模型已同步）")
        st.toast("设置已保存", icon="✅")
