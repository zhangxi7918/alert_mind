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

## 文件上传接口

- feat(models): 添加文件上传响应模型（2026-06-01）
  - 新增 `UploadResponse`，统一描述上传文件名、切分 chunk 数量、处理状态与可选消息。
- feat(api): 添加文件上传入库接口（2026-06-01）
  - 新增 `POST /files/upload`，接收 `UploadFile` 后异步保存到 `uploads/` 目录。
  - 上传内容经文档切分服务处理后写入向量库，并返回统一上传响应。
  - 在 FastAPI 入口以 `/api` 前缀和“文件管理”标签注册文件路由。
  - 增加 `aiofiles` 与 `python-multipart` 依赖以支持异步文件写入和 multipart 表单解析。

## 向量数据库

- feat(vector-db): 添加 Milvus standalone Docker Compose 配置（2026-05-31）
  - 新增 `vector-database.yml`，定义 `etcd`、`minio`、`milvus-standalone` 三个服务。
  - 为 Milvus 持久化数据目录并对外暴露 `19531` 端口。
- feat(milvus): 添加 Milvus collection 连接管理器（2026-05-31）
  - 新增 `MilvusClientManager`，负责连接 Milvus、创建并加载 `biz` collection、关闭时释放资源。
  - 为 `biz` collection 定义 `id`、`vector`、`content`、`metadata` 字段，并在向量字段创建 `IVF_FLAT`/`L2` 索引。
  - 补充 `milvus_host` 与 `milvus_port` 配置项，默认连接本地 `19531` 端口，并统一通过 `_collection_exists()` 判断 collection 是否存在。
- feat(embedding): 添加 DashScope 兼容模式向量化服务（2026-05-31）
  - 新增 `DashScopeEmbeddings`，实现 LangChain `Embeddings` 的文档批量向量化与查询向量化接口。
  - 通过 OpenAI 兼容客户端连接 DashScope embedding API，并固定使用 1024 维向量。
  - 将 DashScope OpenAI 兼容客户端改为首次向量化时懒加载，避免缺少 API key 时在模块导入阶段报错。
- feat(vector-store): 添加 LangChain Milvus 向量存储管理器（2026-05-31）
  - 新增 `VectorStoreManager`，组合 DashScope embedding 服务与 Milvus VectorStore。
  - 暴露 `add_documents()` 与 `similarity_search()` 方法，统一返回插入 id 列表和相似文档列表。
  - 新增局部 `LegacyCompatibleMilvus`，按需补齐 langchain-milvus 读取既有 collection 时需要的旧版连接 alias。
  - 新增 `initialize()` 与 `close()` 管理向量库生命周期，避免模块导入阶段提前连接 Milvus。
  - 写入文档时自动生成 UUID 主键，匹配 `biz` collection 的非自增 `id` 字段。
- feat(rag): 添加向量写入与查询服务（2026-05-31）
  - 新增 `VectorIndexService`，接收切分后的文档块并返回向量库插入数量。
  - 新增 `VectorSearchService`，按 `rag_top_k` 配置执行相似度查询并返回文档列表。
- feat(tools): 添加知识库检索工具函数（2026-06-01）
  - 新增 `retrieve_knowledge` LangChain tool，将向量检索结果按换行拼接为字符串。
  - 在 `app.tools` 包入口导出 `DEFAULT_LOCAL_AGENT_TOOLS`，集中维护 Agent 默认本地工具列表。
  - 增加 `langchain` 依赖以支持 `@tool` 装饰器。
- feat(app): 在 FastAPI lifespan 中接入 Milvus 连接管理（2026-05-31）
  - 服务启动时调用 `vector_store_manager.initialize()`，关闭时调用 `vector_store_manager.close()`。
  - 将 Milvus 生命周期入口从底层 client manager 收口到向量存储管理器。

## 文档切分服务

- feat(splitter): 添加 Markdown 与纯文本切分服务（2026-05-31）
  - 新增 `DocumentSplitterService`，Markdown 先按 `#`/`##` 标题切分，再按字符数切分，普通文本直接按字符数切分。
  - 对相邻小于 300 字符的碎片进行合并，并为切分结果补充 `_source` 与 `_file_name` 元数据。
