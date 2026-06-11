# AlertMind

AlertMind 是一个面向运维场景的智能问答与告警分析项目。它基于 FastAPI、LangGraph、Milvus、Redis 和 Prometheus，提供知识库 RAG 问答、AIOps 诊断流程、文件入库和 Web 聊天界面。

## 主要功能

- RAG 知识库问答：支持上传 TXT、Markdown、PDF、Word 文档后进行检索增强问答。
- 可恢复流式对话：回答过程中刷新页面后，可继续从 Redis Stream 恢复生成状态。
- AIOps 诊断：通过 Plan-Execute 流程调用监控工具，分析 Prometheus 告警和指标。
- 会话管理：支持读取和清空历史会话。
- 前端页面：`/` 提供静态聊天界面，`/docs` 提供 FastAPI 接口文档。

## 技术栈

- 后端：Python 3.11+、FastAPI、Uvicorn
- Agent：LangGraph、LangChain、DashScope Qwen
- 向量库：Milvus
- 状态存储：Redis
- 监控：Prometheus、Node Exporter、FastMCP
- 前端：原生 HTML/CSS/JavaScript

## 本地启动

1. 安装依赖：

   ```bash
   uv sync
   ```

2. 准备环境变量：

   ```bash
   cp .env.example .env
   ```

   至少需要在 `.env` 中配置：

   ```env
   DASHSCOPE_API_KEY=你的 DashScope API Key
   ```

3. 启动依赖服务：

   ```bash
   docker compose -f vector-database.yml -f docker-compose.yml up -d
   ```

4. 启动应用：

   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 9000
   ```

5. 打开页面：

   - Web 聊天界面：http://localhost:9000
   - API 文档：http://localhost:9000/docs
   - Prometheus：http://localhost:9090

## 生产部署

项目内置了 Codex 部署 Skill：`.codex/skills/alert-mind-deploy/SKILL.md`。当需要部署、重新部署、发布、更新或重启服务器上的 AlertMind 时，优先按该 Skill 执行自动化部署：

```bash
bash .codex/skills/alert-mind-deploy/scripts/deploy.sh
```

该脚本会 SSH 到已初始化的远程服务器项目目录，拉取 GitHub `origin/main`，保留服务器侧 `.env`、`uploads`、`logs`、`volumes` 和 Docker 数据卷，重建并启动完整 Compose 栈，最后验证 `/health`。

如果需要手动部署，也可以组合基础服务、向量库和生产覆盖配置启动：

```bash
docker compose -f vector-database.yml -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

部署前请确保服务器已经具备 Docker、Docker Compose、Git 和 SSH 访问能力，项目目录中存在 Git 仓库和生产 `.env`，并配置真实的 `DASHSCOPE_API_KEY` 等必要环境变量。

## 常用命令

```bash
# 运行单元测试
uv run python -m unittest discover

# 批量导入 uploads 目录中的文档
uv run python scripts/batch_index_docs.py

# 运行 RAG 评测
uv run python scripts/evaluate_rag.py
```

## 目录结构

```text
app/                 FastAPI 应用、Agent、服务层和接口
mcp_servers/         MCP 监控工具服务
static/              前端静态页面
uploads/             上传和待入库文档
eval/                RAG 评测数据与脚本
scripts/             文档入库、评测和调试脚本
prometheus/          Prometheus 配置和告警规则
tests/               单元测试
```
