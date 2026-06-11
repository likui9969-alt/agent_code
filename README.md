# AI Code Assistant v2.0

LangGraph + FastAPI + Redis + Streamlit 全栈 AI 代码助手。

## 架构

```
Streamlit (8501)  →  FastAPI (8000)  →  LangGraph  →  Redis
     前端              后端              Agent引擎      Memory
```

## 快速启动

```bash
# 后端
pip install -r requirements.txt
REDIS_ENABLED=false python run.py              # http://localhost:8000

# 前端
pip install -r requirements-frontend.txt
python run_streamlit.py                        # http://localhost:8501
```

## 功能

| 模块 | 说明 |
|------|------|
| 项目浏览器 | 打开本地文件夹、树形文件结构、新建/删除/重命名 |
| 对话历史 | 自动保存 JSON、新建/删除/重命名、点击恢复 |
| 编辑器标签 | 多文件切换、自动保存、修改状态 |
| AI 聊天 | Markdown 渲染、代码高亮、复制按钮 |
| Agent 管道 | 实时显示 Planner→Code→Tools→Review→Human 状态 |
| 文件操作 | Apply/Diff 预览、确认写入 |
| Human-in-the-Loop | Approve/Reject/Modify 审批面板 |
| 设置页面 | 模型选择、API Key、主题、语言 |
| 首页 | 最近项目、最近对话、示例 Prompt |

## 项目结构

```
mvp/
├── app/                      # 后端
│   ├── agents.py / graph.py / llm.py / streaming.py
│   ├── tools/  /  mcp/  /  memory.py
│   └── main.py
├── frontend/                 # 前端 (Streamlit)
│   ├── app.py                # 入口
│   ├── i18n.py               # 中文界面
│   ├── pages/                # home / chat / settings
│   ├── components/           # 8 个 UI 组件
│   └── services/             # api_client / history_store / file_manager
├── data/                     # 本地 JSON 数据
├── Dockerfile / docker-compose.yml
└── .env.production
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /chat | Agent 管道 |
| POST | /chat/stream | SSE 流式 |
| POST | /chat/{id}/resume | 人工决策 |
| GET | /chat/{id}/state | 状态快照 |
| GET | /tools | 工具列表 |
| GET | /mcp | MCP 插件 |
| GET | /health | 健康检查 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| QWEN_API_KEY | — | 通义千问 API Key |
| QWEN_MODEL | qwen-plus | 模型 |
| REDIS_ENABLED | true | Redis 开关 |
