# 服务依赖拓扑文档

本文档描述 alert_mind 平台及其依赖服务的拓扑关系、端口配置和健康检查方式，供故障排查时快速定位依赖链。

## 服务总览

```
                    ┌─────────────────┐
                    │   用户 / 前端    │
                    └────────┬────────┘
                             │ HTTP / SSE
                    ┌────────▼────────┐
                    │  alert-mind-    │
                    │  agent (FastAPI)│
                    │  port: 9000     │
                    └──┬──┬──┬──┬────┘
                       │  │  │  │
           ┌───────────┘  │  │  └────────────────┐
           │              │  │                   │
  ┌────────▼───┐  ┌───────▼──┴──┐  ┌─────────────▼──┐
  │  Milvus    │  │  DashScope  │  │  Prometheus    │
  │  Vector DB │  │  LLM / Emb  │  │  port: 9090    │
  │  port:19531│  │  (External) │  └────────────────┘
  └────────────┘  └─────────────┘
         │
  ┌──────▼─────┐  ┌─────────────┐
  │   etcd     │  │   MinIO     │
  │  port:2379 │  │  port:9001  │
  └────────────┘  └─────────────┘

  ┌─────────────────────────────────────────────────┐
  │  MCP Monitor Server (FastMCP)                   │
  │  port: 8004                                     │
  │  工具：query_metrics / query_alerts             │
  └─────────────────────────────────────────────────┘
```

## 各服务详情

### alert-mind-agent（主服务）

| 属性 | 值 |
|------|----|
| 端口 | 9000 |
| 健康检查 | `GET /api/health` |
| 启动命令 | `uv run uvicorn app.main:app --port 9000` |
| 关键依赖 | Milvus（向量检索）、DashScope（LLM/Embedding）、MCP Monitor Server（告警查询） |

**关键接口：**
- `POST /api/chat` — 非流式问答
- `POST /api/chat/stream` — SSE 流式问答
- `POST /api/files/upload` — 文档上传入库
- `POST /api/aiops/query` — AIOps Plan-Execute 分析
- `GET /api/health` — 健康检查

---

### Milvus（向量数据库）

| 属性 | 值 |
|------|----|
| 端口 | 19531（gRPC）|
| 健康检查 | `curl http://localhost:9091/healthz` |
| 数据存储 | MinIO（对象存储）+ etcd（元数据）|
| Collection | `biz`（向量维度 1024，IVF_FLAT / L2 索引）|
| 启动方式 | `docker compose -f vector-database.yml up -d` |

**故障影响：** Milvus 不可用时，文件上传和知识库检索均失败，但 LLM 问答仍可使用（无 RAG 增强）。

**常见问题：**
- etcd 磁盘写入异常会导致 Milvus 集群不可用
- MinIO 磁盘空间不足会导致向量写入失败

---

### etcd（Milvus 元数据存储）

| 属性 | 值 |
|------|----|
| 端口 | 2379 |
| 健康检查 | `etcdctl endpoint health` |
| 数据目录 | `volumes/etcd/` |

---

### MinIO（Milvus 对象存储）

| 属性 | 值 |
|------|----|
| API 端口 | 9000（注意与主服务冲突，内部使用）|
| 控制台端口 | 9001 |
| 健康检查 | `curl http://localhost:9001/minio/health/live` |
| 数据目录 | `volumes/minio/` |

---

### Prometheus（指标采集）

| 属性 | 值 |
|------|----|
| 端口 | 9090 |
| 健康检查 | `curl http://localhost:9090/-/healthy` |
| 配置文件 | `prometheus/prometheus.yml` |
| 告警规则 | `prometheus/alert_rules.yml` |

**采集目标：**
- Node Exporter（宿主机系统指标）
- alert-mind-agent 业务指标（如有暴露）

---

### MCP Monitor Server（监控工具服务）

| 属性 | 值 |
|------|----|
| 端口 | 8004 |
| 健康检查 | `curl http://localhost:8004/mcp` |
| 启动命令 | `uv run python mcp_servers/monitor_server.py` |
| 传输协议 | streamable-http |

**暴露工具：**
- `query_metrics(promql, time_range)` — 查询 Prometheus 指标
- `query_alerts(status)` — 查询当前告警状态

---

## 故障影响矩阵

| 故障服务 | 影响范围 | 不受影响 |
|----------|----------|----------|
| Milvus 不可用 | 文档上传、知识库检索 | LLM 对话（无 RAG 增强）|
| DashScope API 不可用 | 全部 LLM 功能、文档向量化 | 健康检查接口 |
| MCP Monitor Server 不可用 | AIOps 监控查询工具 | RAG 问答（降级为本地工具）|
| Prometheus 不可用 | 告警数据查询 | 知识库检索、LLM 问答 |
| etcd 不可用 | Milvus 无法启动 | — |
| MinIO 磁盘满 | 向量写入失败 | 已有向量的检索查询 |

## 启动顺序

```
1. etcd + MinIO（Milvus 依赖）
2. Milvus standalone
3. Prometheus + Node Exporter
4. MCP Monitor Server
5. alert-mind-agent
```

建议使用 `docker compose -f vector-database.yml up -d` 启动向量库组件（包含步骤 1-2），等待 Milvus 健康检查通过后再启动主服务。
