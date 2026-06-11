# Contributing to AI Code Assistant

感谢你的关注！欢迎通过 Issue、PR、文档改进等方式参与贡献。

## 行为准则

- 保持尊重和包容的交流态度
- 讨论聚焦技术问题
- 接受建设性批评

## 如何贡献

### 报告 Bug

1. 在 [Issues](../../issues) 中搜索是否已存在相同问题
2. 提供详细的 Bug 描述、复现步骤、环境信息
3. 附上相关日志或截图

### 提交代码

1. **Fork** 本仓库
2. **创建分支**：`git checkout -b feat/your-feature`
3. **编写代码**：遵循项目现有代码风格
4. **运行测试**：确保所有测试通过

```bash
REDIS_ENABLED=false QWEN_API_KEY="" python test_graph.py
REDIS_ENABLED=false QWEN_API_KEY="" python test_stream.py
REDIS_ENABLED=false QWEN_API_KEY="" python test_mcp.py
python test_frontend.py
```

5. **提交 PR**：描述修改内容、原因、测试情况

### 代码规范

- 所有 Python 函数使用 Type Hints
- Docstring 使用 Google 风格
- 安全相关修改必须包含测试用例
- 不引入不必要的新依赖

## 项目结构

```
mvp/
├── app/           # 后端 — 不要修改 API 接口签名
├── frontend/      # 前端 — 组件间通过 session_state 通信
├── test_*.py      # 测试 — LLM 调用统一 Mock
```

## 开发环境

```bash
pip install -r requirements.txt
pip install -r requirements-frontend.txt
cp .env.example .env
# 编辑 .env，填入开发用的 QWEN_API_KEY
```

关闭 Redis 进行本地开发：

```bash
REDIS_ENABLED=false python run.py --no-reload
```

## 安全原则

- **永远不要**在代码中硬编码 API Key
- **永远不要**提交 `.env` 文件
- 使用 `secrets.compare_digest` 比较 Token
- 新增工具必须通过 `ToolPolicy` 检查
- 所有文件操作必须通过 `resolve_path` 路径验证

---

再次感谢你的贡献！
