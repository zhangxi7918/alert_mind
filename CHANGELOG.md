## 项目目录结构

- chore(app): 初始化应用包目录结构（2026-05-30）
  - 新增 `app/api`、`app/services`、`app/core`、`app/models`、`app/tools`、`app/agent` 目录。
  - 为 `app` 及其子目录添加 `__init__.py`，便于后续按 Python 包组织代码。
  - 补充 `static` 和 `uploads` 资源目录，并添加占位文件便于版本控制追踪。
- feat(config): 添加应用配置 Settings 类（2026-05-30）
  - 新增 `app/config.py`，通过 `pydantic_settings.BaseSettings` 定义基础配置项和默认值。
  - 配置 `model_config` 读取 UTF-8 编码的 `.env` 文件、关闭环境变量大小写敏感，并忽略多余配置项。
  - 增加 `app_version` 配置项，为健康检查等接口提供统一版本来源。

## 服务入口

- feat(app): 初始化 FastAPI 服务入口（2026-05-30）
  - 将 `app/main.py` 改为 FastAPI 应用入口，从配置读取服务标题和版本。
  - 添加 lifespan 启动日志、开发期 CORS 中间件，并注册健康检查路由。

## 健康检查接口

- feat(api): 添加健康检查路由（2026-05-30）
  - 新增 `app/api/health.py`，定义 `APIRouter` 和 `GET /health` 接口。
  - 接口返回 `status` 与从配置读取的 `version` 字段。

## 向量数据库

- feat(vector-db): 添加 Milvus standalone Docker Compose 配置（2026-05-31）
  - 新增 `vector-database.yml`，定义 `etcd`、`minio`、`milvus-standalone` 三个服务。
  - 为 Milvus 持久化数据目录并对外暴露 `19531` 端口。
- feat(milvus): 添加 Milvus collection 连接管理器（2026-05-31）
  - 新增 `MilvusClientManager`，负责连接 Milvus、创建并加载 `biz` collection、关闭时释放资源。
  - 为 `biz` collection 定义 `id`、`vector`、`content`、`metadata` 字段，并在向量字段创建 `IVF_FLAT`/`L2` 索引。
  - 补充 `milvus_host` 与 `milvus_port` 配置项，默认连接本地 `19531` 端口，并统一通过 `_collection_exists()` 判断 collection 是否存在。
- feat(app): 在 FastAPI lifespan 中接入 Milvus 连接管理（2026-05-31）
  - 服务启动时调用 `milvus_manager.connect()`，关闭时调用 `milvus_manager.close()`。

## 文档切分服务

- feat(splitter): 添加 Markdown 与纯文本切分服务（2026-05-31）
  - 新增 `DocumentSplitterService`，Markdown 先按 `#`/`##` 标题切分，再按字符数切分，普通文本直接按字符数切分。
  - 对相邻小于 300 字符的碎片进行合并，并为切分结果补充 `_source` 与 `_file_name` 元数据。
