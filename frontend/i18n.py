"""国际化 — 中文界面 (Internationalization — Chinese UI)."""

from __future__ import annotations

T = {
    # ── 通用 ──
    "app_title": "🧠 AI 代码助手",
    "app_subtitle": "规划 → 编码 → 工具 → 审查 → 人工确认",
    "send": "发送",
    "cancel": "取消",
    "save": "保存",
    "delete": "删除",
    "rename": "重命名",
    "refresh": "刷新",
    "close": "关闭",
    "confirm": "确认",
    "loading": "加载中...",
    "no_data": "暂无数据",
    "success": "操作成功",
    "error": "操作失败",
    "copy": "复制",
    "copied": "已复制",

    # ── 侧边栏 ──
    "project": "📁 项目",
    "open_folder": "打开项目",
    "switch_project": "切换项目",
    "new_file": "新建文件",
    "delete_file": "删除文件",
    "rename_file": "重命名文件",
    "refresh_files": "刷新文件",
    "file_tree": "文件结构",
    "no_project": "未打开项目",

    # ── 对话历史 ──
    "chat_history": "💬 历史记录",
    "new_chat": "新建对话",
    "delete_chat": "删除对话",
    "rename_chat": "重命名对话",
    "no_history": "暂无历史记录",
    "search_chat": "搜索对话...",
    "today": "今天",
    "yesterday": "昨天",
    "earlier": "更早",

    # ── 编辑器 ──
    "editor": "📝 编辑器",
    "no_file_open": "未打开文件",
    "unsaved": "未保存",
    "saved": "已保存",
    "modified": "● 已修改",
    "close_tab": "关闭标签",
    "close_all": "关闭全部",
    "close_others": "关闭其他",

    # ── AI 聊天 ──
    "chat_placeholder": "描述你想要构建的功能...",
    "continue_chat": "继续生成",
    "regenerate": "重新生成",
    "user_message": "用户",
    "ai_message": "AI 助手",
    "thinking": "思考中...",
    "generating": "代码生成中...",

    # ── Agent 执行 ──
    "agent_pipeline": "🔧 执行流程",
    "planner": "规划器",
    "planner_desc": "分析需求，生成实现计划",
    "code_agent": "代码生成器",
    "code_agent_desc": "根据计划生成代码",
    "tool_exec": "工具执行",
    "tool_exec_desc": "读写文件、搜索代码",
    "reviewer": "代码审查",
    "reviewer_desc": "自动检查代码质量",
    "human_approval": "人工确认",
    "human_approval_desc": "等待您的审核",
    "status_pending": "等待中",
    "status_running": "执行中",
    "status_complete": "已完成",
    "status_error": "出错",

    # ── 代码审查 ──
    "review_passed": "✅ 所有检查通过",
    "review_failed": "❌ 发现问题",
    "approve": "✅ 通过",
    "reject": "❌ 驳回",
    "modify": "📝 修改",
    "reject_reason": "驳回原因（可选）：",
    "modify_instruction": "修改意见：",
    "confirm_approve": "确认通过",
    "confirm_reject": "确认驳回",
    "confirm_modify": "确认修改",
    "waiting_approval": "⏸️ 等待您的审核...",

    # ── 文件操作 ──
    "apply_code": "应用代码",
    "create_file": "创建文件",
    "overwrite_file": "覆盖文件",
    "show_diff": "查看差异",
    "diff_title": "代码差异",
    "confirm_overwrite": "确认覆盖",
    "file_created": "文件已创建",
    "file_updated": "文件已更新",

    # ── 设置 ──
    "settings": "⚙️ 设置",
    "model_select": "模型选择",
    "api_key": "API Key",
    "api_key_hint": "输入你的 API Key",
    "theme": "主题",
    "theme_light": "浅色",
    "theme_dark": "暗色",
    "language": "语言",
    "language_zh": "中文",
    "language_en": "English",
    "auto_save": "自动保存",
    "backend_url": "后端地址",

    # ── 首页 ──
    "home": "🏠 首页",
    "welcome": "欢迎使用 AI 代码助手",
    "recent_projects": "最近项目",
    "recent_chats": "最近对话",
    "quick_start": "快速开始",
    "example_prompts": "示例提示词",
    "new_project": "新建项目",
    "open_project": "打开已有项目",

    # ── 提示词示例 ──
    "example_1": "用 Python 写一个快速排序算法",
    "example_2": "创建一个 FastAPI CRUD 接口",
    "example_3": "写一个斐波那契数列函数",
    "example_4": "帮我审查这段代码的安全性",
    "example_5": "重构这个函数使其更高效",
    "example_6": "为这个模块生成 API 文档",
}

# ── 便捷函数 ──
def t(key: str, default: str = "") -> str:
    """获取翻译文本。"""
    return T.get(key, default or key)
