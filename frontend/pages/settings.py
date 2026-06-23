"""设置页 — 模型 / API Key / 语言 / 主题 / 后端地址。"""

from __future__ import annotations

import os

import streamlit as st

from frontend.config import API_BASE_URL
from frontend.i18n import t
from frontend.services.api_client import APIClient
from frontend.utils.session import persist_setting, persist_settings


_MODEL_OPTIONS = ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-plus-latest"]


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
    current_model = _MODEL_OPTIONS[st.session_state.get("settings_model_idx", 0)]
    model = st.selectbox(
        "选择模型",
        options=_MODEL_OPTIONS,
        index=_MODEL_OPTIONS.index(current_model),
    )
    if model:
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

    st.divider()

    # ── 语言 ──
    st.subheader("🌐 语言 / Language")
    lang_label = st.radio(
        "界面语言", options=["中文", "English"], horizontal=True,
        index=0 if st.session_state.get("lang", "zh") == "zh" else 1,
    )
    lang = "zh" if lang_label == "中文" else "en"

    st.divider()

    # ── 主题 ──
    st.subheader("🎨 主题")
    theme_idx = st.radio(
        "颜色主题",
        options=["浅色", "暗色", "跟随系统"],
        horizontal=True,
        index=st.session_state.get("theme_idx", 0),
    )
    theme_idx = ["浅色", "暗色", "跟随系统"].index(theme_idx)

    st.divider()

    # ── 后端地址 ──
    st.subheader("🔗 后端服务")
    backend = st.text_input(
        "API 地址",
        value=st.session_state.get("api_base_url", "http://localhost:8000"),
    )

    st.divider()

    # ── 自动保存 ──
    auto = st.toggle("自动保存对话", value=st.session_state.get("auto_save", True))

    # ── 保存按钮 ──
    if st.button("💾 保存设置", type="primary", use_container_width=True):
        # Persist API key only when provided (allow clearing)
        persisted_key = api_key if api_key else ""
        persist_settings(
            model=model,
            api_key=persisted_key,
            lang=lang,
            theme_idx=theme_idx,
            api_base_url=backend,
            auto_save=auto,
        )
        st.session_state["settings_model_idx"] = _MODEL_OPTIONS.index(model)
        os.environ["QWEN_MODEL"] = model

        key_for_backend = persisted_key if persisted_key else None
        if _push_llm_settings(api_key=key_for_backend, model=model):
            st.success("✅ 设置已保存并同步到后端")
        else:
            st.success("✅ 设置已保存（模型已同步）")
        st.toast("设置已保存", icon="✅")
        st.rerun()
