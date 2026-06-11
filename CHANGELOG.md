# Changelog

All notable changes to AI Code Assistant will be documented in this file.

---

## [1.0.0] — 2026-06-11

### 🚀 新增功能

- **LangGraph Agent 管道** — Planner → Code Agent → Tool Executor → Reviewer → Human-in-the-Loop
- **SSE 流式输出** — 实时推送管道执行状态、工具调用结果、中断事件
- **Human-in-the-Loop** — LangGraph `interrupt()` 实现审批面板（通过/驳回/修改）
- **Redis 持久化** — Session Memory 管理 + Checkpoint Saver（JSON 序列化）
- **MCP 插件系统** — 可扩展工具插件架构，支持运行时加载/卸载/重载
- **FileMCP** — 文件读写、目录列表、正则搜索的 MCP 插件实现
- **原生工具系统** — ReadFile、WriteFile、Grep、ListFiles、RunPython 工具
- **项目浏览器** — 侧边栏目录树、文件打开/创建/删除
- **编辑器标签** — 多文件标签、Diff 磁盘对比、保存到磁盘
- **对话历史** — JSON 文件持久化、搜索、重命名、删除、恢复
- **Apply + Diff** — AI 生成代码的差异预览与一键写入
- **国际化** — 中文/English 界面切换
- **Bearer Token 认证** — 时序攻击防护 (`secrets.compare_digest`)
- **Session 所有权模型** — Token hash 绑定会话，403 未授权拦截
- **API 速率限制** — 滑动窗口算法 (Redis ZSET + 内存回退)
- **CORS 中间件** — 安全配置，防止 `*` + `credentials=true` 组合
- **Prompt Injection 防护** — `<PRIORITY>` 标签 + `<UserRequest>` 边界 + 工具策略卫士
- **路径遍历防护** — 绝对路径拒绝 + 规范边界检查 + 符号链接检测
- **Docker 生产部署** — 多阶段构建、非 root 用户、健康检查

### 🔧 优化内容

- LLM 调用 4 次指数退避重试 (0s, 1s, 2s, 4s)
- API Key 日志脱敏 (`_sanitize_error`)
- 代码归一化比较 (`_normalize_code`) 防止自动修复无限循环
- 工具执行日志改用 `deque(maxlen=500)` 防止内存溢出
- Checkpoint 存储 v2: 单 Thread Blob → 分 Thread Hash 存���
- Graph 构建移入 lifespan 确保 Redis 就绪后初始化

### 🐛 修复内容

- Redis Checkpoint 序列化从 pickle 迁移为 JSON（消除 RCE 风险）
- `review["issues"]` 增加类型校验和安全降级
- `list_tools_by_source` 类型声明与实现一致
- FileMCP 参数防御性检查 (`args.get()` 替代 `args[]`)
- `_write_done` / `_run_done` 规范化为 `_code_equivalent`
- 测试 Mock 路径修复 (`app.llm.chat` → `app.agents.chat`)
- SSE `_sanitize` 补充 `input` / `session_id` 字段
- `run_streamlit.py` 嵌套启动防护

### ⚠️ 已知问题

- `run_python` 工具仅执行语法校验，不真正运行代码（设计如此）
- `git_mcp` 为接口占位，Git 操作尚未实现
- 多 Worker 部署时 `InMemorySaver` 本地缓存仅在每次 `aget_tuple` 时刷新（Redis 是唯一事实来源）
- 前端未适配移动端响应式布局

### 📋 未来计划

- [ ] Git 操作 (GitPython 实现)
- [ ] Python 代码沙箱执行
- [ ] OAuth2 / OIDC 认证
- [ ] PostgreSQL Checkpoint 后端
- [ ] LangSmith / LangFuse 可观测性集成
- [ ] 单元测试覆盖率 > 80%
- [ ] VS Code Extension
