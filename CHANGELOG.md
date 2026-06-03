## Logger 文件配置

- feat(main): 新增 HTTP 请求日志中间件，自动记录方法、路径、状态码、耗时（2026-06-03）
- feat(logger): 新增 `app/utils/logger.py`，统一配置 loguru 文件输出（2026-06-03）
  - 按天轮转（`rotation="00:00"`），保留 7 天（`retention="7 days"`）
  - 文件级别 DEBUG，控制台级别 INFO，均使用统一格式；`main.py` 在模块加载时调用 `setup_logger()`
  - 日志写入 `logs/alert_mind_YYYY-MM-DD.log`

## 项目目录结构

- chore(app): 初始化应用包目录结构（2026-05-30）
  - 新增 `app/api`、`app/services`、`app/core`、`app/models`、`app/tools`、`app/agent` 目录。
  - 为 `app` 及其子目录添加 `__init__.py`，便于后续按 Python 包组织代码。
  - 补充 `static` 和 `uploads` 资源目录，并添加占位文件便于版本控制追踪。
- feat(config): 添加应用配置 Settings 类（2026-05-30）
  - 新增 `app/config.py`，通过 `pydantic_settings.BaseSettings` 定义基础配置项和默认值。
  - 配置 `model_config` 读取 UTF-8 编码的 `.env` 文件、关闭环境变量大小写敏感，并忽略多余配置项。
  - 增加 `app_version` 配置项，为健康检查等接口提供统一版本来源。
- fix(config): 移除硬编码 DashScope API Key（2026-06-02）
  - `DASHSCOPE_API_KEY` 改为仅从 `.env` 或环境变量读取，缺失时通过统一 helper 抛出明确错误。
  - 新增 `.env.example`，提供本地配置模板且不包含真实密钥。

## 服务入口

- feat(app): 初始化 FastAPI 服务入口（2026-05-30）
  - 将 `app/main.py` 改为 FastAPI 应用入口，从配置读取服务标题和版本。
  - 添加 lifespan 启动日志、开发期 CORS 中间件，并注册健康检查路由。
- feat(app): 挂载静态前端资源并提供首页入口（2026-06-01）
  - 新增 `/static` 静态资源挂载，支持浏览器直接访问前端页面与资源。
  - 新增根路径 `/`，优先返回 `static/index.html`，缺失时回退到 API 欢迎信息。

## 前端聊天界面

- feat(static): 添加智能 AlertMind 助手 Web 聊天界面（2026-06-01）
  - 新增 `static/index.html`、`static/app.js` 与 `static/styles.css`，提供侧边栏、聊天区、模式选择、文件上传入口和 AI Ops 操作入口。
  - 前端支持快速问答、流式问答、Markdown/代码高亮渲染、本地历史对话管理与通知反馈。
  - 补充响应式布局、消息气泡、加载遮罩、上传状态和智能运维详情折叠样式。
- fix(static): 将前端 API 基础地址改为本地 9000 端口（2026-06-01）
  - 把 `apiBaseUrl` 从 `http://localhost:9900/api` 调整为 `http://localhost:9000/api`，避免请求打到其他本地服务。
- fix(static): 对齐前端请求与 FastAPI 接口契约（2026-06-01）
  - 聊天接口改为提交 `question` 与 `session_id`，避免因字段名不匹配返回 422。
  - 流式聊天路径改为 `/api/chat/stream`，文件上传路径改为 `/api/files/upload`，并按当前后端响应结构判断成功。
- fix(static): 根据入库统计展示文件上传结果（2026-06-02）
  - 前端读取 `inserted_count` 与 `skipped_count`，区分首次入库、部分重复和全部重复上传。
  - 全部重复时提示“内容已存在，未重复入库”，避免固定成功文案误导用户。
  - 首页和静态资源统一返回 no-cache 响应头，避免后续前端更新依赖手动版本查询串。
- fix(static): 默认知识库问答接入流式聊天接口（2026-06-02）
  - 前端默认对话模式改为 `stream`，进入页面后直接请求 `/api/chat/stream`。
  - 初始模式文案和下拉选中状态同步显示为“流式”，保留“快速”作为手动回退模式。

## RAG Agent 服务

- feat(mcp): 添加模拟监控 MCP 服务入口（2026-06-01）
  - 新增 `mcp_servers/monitor_server.py`，通过 FastMCP 暴露 `query_metrics` 与 `query_alerts` 两个模拟监控工具。
  - 补充 MCP 监控服务地址和传输协议配置，并添加 `fastmcp` 依赖。
- feat(mcp): 添加 MCP Client 创建与工具加载封装（2026-06-01）
  - 新增 `app/agent/mcp_client.py`，从配置构造 monitor MCP server 连接并创建 `MultiServerMCPClient`。
  - 提供带重试的 client 初始化、安全工具加载和异常链格式化方法。
  - 在 RAG Agent、AIOps planner 和 executor 中合并本地工具与 MCP 工具，加载失败时保留本地工具链路。
  - 展开 `ExceptionGroup` 内部异常，让 MCP 连接失败日志能显示真实底层错误。
- feat(agent): 添加 RAG Agent 服务封装（2026-06-01）
  - 新增 `RagAgentService`，组合 `ChatQwen`、`MemorySaver` 和本地知识库工具创建可复用 Agent。
  - 提供非流式 `query()` 与流式 `query_stream()` 方法，并通过 `session_id` 隔离对话历史。
- feat(models): 添加聊天请求模型（2026-06-01）
  - 新增 `ChatRequest`，统一描述用户问题 `question` 与会话标识 `session_id`。
- feat(api): 添加 RAG 聊天接口（2026-06-01）
  - 新增 `POST /chat` 非流式问答接口，返回 `answer` 与 `session_id`。
  - 新增 `POST /chat/stream` SSE 流式问答接口，将 Agent chunk 序列化为 JSON 事件数据。
  - 在 FastAPI 入口以 `/api` 前缀和“智能问答”标签注册聊天路由。
- fix(agent): 显式配置 DashScope 国内兼容模式地址（2026-06-01）
  - 为 `ChatQwen` 设置 `base_url`，避免默认请求国际站导致国内 DashScope API Key 认证失败。
- feat(agent): 添加 AIOps 执行状态类型定义（2026-06-01）
  - 新增 `app/agent/aiops` 子包与 `PlanExecuteState`，统一描述输入、计划、已执行步骤和最终响应字段。
- feat(aiops): 添加 Plan 结构化输出模型和规划提示词（2026-06-01）
  - 新增 `app/agent/aiops/planner.py`，用 Pydantic `BaseModel` 约束计划输出必须包含 `steps` 字符串数组。
  - 使用 `ChatPromptTemplate.from_messages()` 定义专家规划器 prompt，预留工具列表、经验上下文和消息占位符。
  - 实现异步 `planner(state)`，先检索经验文档和格式化工具描述，再通过结构化输出生成计划步骤。
- feat(aiops): 添加计划步骤执行器（2026-06-01）
  - 新增异步 `executor(state)`，从 `plan` 取出当前步骤并交给 LangGraph ReAct Agent 自动完成工具调用循环。
  - 执行完成后记录 `(当前步骤, 执行结果)` 到 `past_steps`，并移除已执行的计划步骤。
  - 包入口改为懒加载导出，避免导入单个子模块时提前加载其他 Agent 依赖，并兼容手动调用时缺少 `past_steps` 的状态增量。
- feat(aiops): 添加计划重审裁判节点（2026-06-01）
  - 新增异步 `replanner(state)`，将原始任务、已完成步骤和剩余计划交给 LLM 判断是否完成。
  - 使用结构化输出约束裁判返回最终 `response` 或调整后的 `plan`，用于驱动后续 Graph 分支。
- feat(aiops): 添加 Plan-Execute 图服务封装（2026-06-01）
  - 新增 `AIOpsService`，用 LangGraph `StateGraph` 串联 planner、executor、replanner 三个节点。
  - 暴露异步 `run(input_text)` 入口，初始化图状态并返回最终执行状态。
- feat(api): 添加 AIOps SSE 查询接口（2026-06-01）
  - 新增 `AiopsRequest` 请求模型和 `POST /api/aiops/query` 路由。
  - 接口通过 `EventSourceResponse` 逐步输出 Plan-Execute Graph 节点执行结果。
- fix(aiops): 对齐 AI Ops 前端按钮与 SSE 接口契约（2026-06-01）
  - 前端按钮改为请求 `POST /api/aiops/query`，并提交 `input` 字段作为智能运维分析任务。
  - AIOps SSE 接口将 Graph 节点输出转换为前端可渲染的计划、步骤完成和报告事件。
  - 为 `static/app.js` 引入版本查询串，避免 Chrome 继续复用旧脚本导致按钮请求旧路径。
- fix(aiops): 增强 AI Ops SSE 阶段流式反馈（2026-06-02）
  - AIOps LangGraph 节点通过 custom stream 输出规划、执行和复核阶段状态。
  - 服务端同时消费 `custom` 与 `updates` 流事件，并为 SSE 响应添加禁止缓冲的响应头。
  - 前端改为按 SSE 事件块解析 AIOps 响应，避免依赖字段形状固定的 JSON 正则。
- fix(aiops): 优化 AI Ops 流式内容排版（2026-06-02）
  - 流式更新阶段同步渲染 Markdown，避免内容完成前只显示拥挤纯文本。
  - 将计划、状态、步骤结果和诊断报告拼接为可扫读的 Markdown 分区。
  - 增加 AIOps 消息标题、状态块和步骤块样式，提升长报告流式阅读体验。
- fix(aiops): 避免 AIOps SSE 中断只显示 network error（2026-06-02）
  - 前端 API 地址改为跟随当前页面 origin，避免 `localhost` 与 `127.0.0.1` 不一致造成请求失败。
  - 后端 SSE 生成器捕获运行时异常并返回 `error` 事件，避免连接被异常关闭。
  - 前端读流中断时保留已渲染内容，并将中断原因追加为错误提示块。
  - Planner 和 Replanner 结构化输出为空时使用保底计划或兜底报告，避免 `NoneType` 导致流中断。
  - 知识库检索失败时返回降级提示，避免 Milvus collection 未加载等向量库异常打断 AIOps 流。
- refactor(aiops): 将 AIOps SSE 输出统一转换为业务事件协议（2026-06-03）
  - Service 层统一将 LangGraph `custom` 与 `updates` 流转换为 `status`、`plan`、`step_complete`、`plan_update`、`report` 和 `complete` 事件。
  - `past_steps` 改用 LangGraph reducer 增量追加，executor 仅返回当前步骤结果，避免历史步骤重复输出。
  - 前端兼容新事件字段渲染计划、步骤结果和后续计划更新，并补充事件转换单测。
  - AIOps 前端改为结构化状态面板，状态和计划更新复用固定区域，避免过程日志挤占诊断报告。
  - 诊断报告支持前端分块揭示，并为运行状态和当前步骤增加轻量动效，保留流式推进感。

## 知识库 Runbook 文档

- feat(knowledge): 添加四篇运维 Runbook 并上传至向量知识库（2026-06-03）
  - 新增 `uploads/runbook_high_cpu.md`：高 CPU 使用率处理手册，含 Prometheus 查询、进程定位、临时缓解和升级路径。
  - 新增 `uploads/runbook_high_memory.md`：内存不足处理手册，含 `MemAvailable` 说明、OOM Kill 查看命令和 Swap 处置方法。
  - 新增 `uploads/runbook_disk_space.md`：磁盘空间告警处理手册，含大文件定位、Docker 清理和 logrotate 建议。
  - 新增 `uploads/runbook_service_timeout.md`：服务响应超时处理手册，含数据库慢查询、GC 停顿排查和熔断降级策略。
  - 通过 `POST /api/files/upload` 入库，共 9 个 chunks 写入 Milvus 向量库；RAG 检索测试验证 CPU 查询精确命中对应手册。

## Prometheus 监控接入

- feat(prometheus): 添加 Prometheus + Node Exporter 本地监控环境（2026-06-03）
  - 新增 `docker-compose.yml`，定义 `alert_mind_prometheus`（9090）和 `alert_mind_node_exporter`（9100）两个容器。
  - 新增 `prometheus/prometheus.yml`，配置 15s 采集间隔并指向 node_exporter 采集目标。
  - 新增 `prometheus/alert_rules.yml`，定义高 CPU（>80% 持续 30s）、高内存（>85%）、高磁盘（>90%）三条告警规则。
- feat(mcp): 为 monitor_server 添加真实 Prometheus 查询工具（2026-06-03）
  - 新增 `query_active_alerts(severity?)`，调用 Prometheus `/api/v1/alerts` 返回当前 firing/pending 告警。
  - 新增 `query_metric_history(metric, duration_minutes, step_seconds)`，调用 `/api/v1/query_range` 返回 CPU/内存/磁盘历史曲线，含 max/avg 摘要。
  - `config.py` 新增 `prometheus_base_url` 配置项，默认 `http://localhost:9090`。
  - 保留原有 `query_metrics` / `query_alerts` 模拟工具，与真实工具并存。
- fix(static): 修正 AI Ops 默认触发 prompt，使 Agent 优先调用真实 Prometheus 工具（2026-06-03）
  - 将前端默认 prompt 从泛化的"常见告警分析"改为明确指定调用 `query_active_alerts` 和 `query_metric_history`。

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
- fix(api): 加强文件上传入库校验并返回去重统计（2026-06-02）
  - 后端限制上传扩展名、文件大小、UTF-8 编码和空内容，避免无效文件进入切分和向量写入流程。
  - 上传响应新增实际入库数与重复跳过数，便于区分切分数量和新增向量数量。

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
- fix(vector-store): 使用 chunk hash 全库去重后再写入向量库（2026-06-02）
  - 为每个 chunk 补充 `chunk_index` 与 `content_hash` 元数据，并以 `content_hash` 作为新写入主键。
  - 写入前跳过同批重复 chunk 和 Milvus 中已存在的主键，避免重复上传产生重复向量。
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
