---
name: alert-mind-deploy
description: 将 GitHub main 分支的 AlertMind 项目通过 SSH、Git 和 Docker Compose 部署到用户的远程服务器。用户要求部署、重新部署、发布、更新或重启服务器上的 AlertMind 时使用。
---

# AlertMind 部署

只在 `alert_mind` 仓库内使用这个 Skill。

## 目标

把 GitHub 远程仓库 `origin/main` 部署到已经初始化过的远程服务器项目目录，保留服务器侧的 `.env`、`uploads`、`logs`、`volumes` 和 Docker 数据卷，重新构建 Docker 镜像，启动完整 Compose 栈，然后验证 `/health`。

远程服务器必须已经具备 Docker、Docker Compose、Git、SSH 访问能力，并且项目目录中已经存在 Git 仓库和生产 `.env`，例如 `DASHSCOPE_API_KEY`。

## 部署流程

1. 确认目标服务器、用户、端口和项目目录由本机私有配置或环境变量提供，不在 Skill 中维护具体值。
2. SSH 到服务器后，脚本会进入已有项目目录；目录不存在或不是 Git 仓库时直接失败，不自动创建新目录。
3. 从 GitHub 拉取 `origin/main`：

```bash
git fetch origin main:refs/remotes/origin/main
git switch main
git merge --ff-only origin/main
```

如果服务器仓库存在未提交的代码改动，或者本地分支不能 fast-forward 到 `origin/main`，部署会失败，避免静默覆盖服务器上的改动。

4. 运行部署脚本：

```bash
bash .codex/skills/alert-mind-deploy/scripts/deploy.sh
```

5. 如果脚本提示远程 `.env` 缺失，先 SSH 到服务器，用 `.env.example` 创建 `.env` 并填入生产密钥，然后重新运行脚本。
6. 完成后汇报部署的 commit、应用访问地址、健康检查结果，以及任何未运行或不健康的容器。

除非用户明确要求，否则不要上传本地 `.env`，也不要用本地工作树覆盖服务器代码。
