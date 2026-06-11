---
name: alert-mind-deploy
description: 将当前仓库中的 AlertMind 项目通过 SSH、rsync 和 Docker Compose 部署到用户的远程服务器。用户要求部署、重新部署、发布、更新或重启服务器上的 AlertMind 时使用。
---

# AlertMind 部署

只在 `alert_mind` 仓库内使用这个 Skill。

## 目标

把当前工作树部署到远程服务器，保留服务器侧的 `.env`、`uploads`、`logs` 和 `volumes`，重新构建 Docker 镜像，启动完整 Compose 栈，然后验证 `/health`。

## 一次性本地配置

在开发机器上创建 `.codex/skills/alert-mind-deploy/deploy.local.env`。这个文件已被 Git 和 Docker 构建上下文忽略。

```bash
ALERT_MIND_DEPLOY_HOST=your.server.ip
ALERT_MIND_DEPLOY_USER=root
ALERT_MIND_DEPLOY_PORT=22
ALERT_MIND_DEPLOY_DIR=/opt/alert_mind
# ALERT_MIND_SSH_KEY=~/.ssh/id_ed25519
```

可选覆盖项：

```bash
ALERT_MIND_COMPOSE_FILES="vector-database.yml docker-compose.yml docker-compose.prod.yml"
ALERT_MIND_HEALTH_URL=http://127.0.0.1:9000/health
```

远程服务器必须已经具备 Docker、Docker Compose、SSH 访问能力，并且 `${ALERT_MIND_DEPLOY_DIR}/.env` 中已经配置生产密钥，例如 `DASHSCOPE_API_KEY`。

## 部署流程

1. 先用 `git status --short` 检查本地状态；不要回滚无关改动。
2. 验证组合后的 Compose 文件，避免打印完整配置和密钥：

```bash
docker compose -f vector-database.yml -f docker-compose.yml -f docker-compose.prod.yml config --services
```

3. 运行部署脚本：

```bash
bash .codex/skills/alert-mind-deploy/scripts/deploy.sh
```

4. 如果脚本提示远程 `.env` 缺失，先 SSH 到服务器，用 `.env.example` 创建 `.env` 并填入生产密钥，然后重新运行脚本。
5. 完成后汇报应用访问地址、健康检查结果，以及任何未运行或不健康的容器。

除非用户明确要求，否则不要上传本地 `.env`。
