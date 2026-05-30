## 项目目录结构

- chore(app): 初始化应用包目录结构（2026-05-30）
  - 新增 `app/api`、`app/services`、`app/core`、`app/models`、`app/tools`、`app/agent` 目录。
  - 为 `app` 及其子目录添加 `__init__.py`，便于后续按 Python 包组织代码。
  - 补充 `static` 和 `uploads` 资源目录，并添加占位文件便于版本控制追踪。
- feat(config): 添加应用配置 Settings 类（2026-05-30）
  - 新增 `app/config.py`，通过 `pydantic_settings.BaseSettings` 定义基础配置项和默认值。
  - 配置 `model_config` 读取 UTF-8 编码的 `.env` 文件、关闭环境变量大小写敏感，并忽略多余配置项。
