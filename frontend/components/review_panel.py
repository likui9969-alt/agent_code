"""Human-in-the-Loop 审批面板 — 中文 Approve / Reject / Modify。"""

from __future__ import annotations

import streamlit as st


def render_review_panel(review: dict, on_decision) -> None:
    """渲染审批面板。review = {"passed": bool, "issues": [...]}"""
    if not review:
        return
    passed = review.get("passed", False)
    issues = review.get("issues", [])

    st.divider()
    st.subheader("🔍 代码审查结果")

    if passed and not issues:
        st.success("✅ 所有检查通过")
    else:
        st.error(f"❌ {len(issues)} 个问题")
        for issue in issues:
            st.caption(f"  • {issue}")

    st.markdown("### 请做出决策")
    mode = st.session_state.get("review_decision_mode")

    if mode == "reject":
        fb = st.text_area("驳回原因", key="reject_fb", placeholder="请说明驳回原因...")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认驳回", type="primary", use_container_width=True, key="confirm_reject"):
                on_decision("rejected", fb)
                st.session_state["review_decision_mode"] = None
                st.rerun()
        with c2:
            if st.button("取消", use_container_width=True, key="cancel_reject"):
                st.session_state["review_decision_mode"] = None
                st.rerun()
        return

    if mode == "modify":
        fb = st.text_area("修改意见", key="modify_fb", placeholder="请描述需要修改的内容...")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认修改", type="primary", use_container_width=True, key="confirm_modify"):
                on_decision("modify", fb)
                st.session_state["review_decision_mode"] = None
                st.rerun()
        with c2:
            if st.button("取消", use_container_width=True, key="cancel_modify"):
                st.session_state["review_decision_mode"] = None
                st.rerun()
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ 通过", type="primary", use_container_width=True, key="btn_approve"):
            on_decision("approved", "")
            st.rerun()
    with c2:
        if st.button("❌ 驳回", use_container_width=True, key="btn_reject"):
            st.session_state["review_decision_mode"] = "reject"
            st.rerun()
    with c3:
        if st.button("📝 修改", use_container_width=True, key="btn_modify"):
            st.session_state["review_decision_mode"] = "modify"
            st.rerun()


def show_paused_banner(thread_id: str) -> None:
    st.info(f"⏸️ 等待您的审核 — {thread_id[:8]}...")
