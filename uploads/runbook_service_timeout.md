# 服务响应超时处理手册

## 告警说明

告警名称：ServiceResponseTimeout / HighLatency
触发条件：HTTP 请求 P99 延迟超过 2000ms，持续 3 分钟
严重等级：Warning（P99 > 2s）/ Critical（P99 > 5s 或错误率 > 5%）
负责团队：后端研发组 + 基础设施运维组

## 排查步骤

### 第一步：确认响应时间异常

Prometheus 查询 P99 延迟：

```
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))
```

确认是所有接口慢还是特定接口慢，缩小排查范围。

### 第二步：排查上游依赖

服务响应超时通常由以下依赖链中的某一环引起：

**数据库响应慢**：

```bash
# MySQL 查看慢查询
SHOW PROCESSLIST;
SELECT * FROM information_schema.PROCESSLIST WHERE TIME > 10 ORDER BY TIME DESC;

# PostgreSQL
SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;

# MongoDB
db.currentOp({ "active": true, "secs_running": { "$gt": 5 } })
```

**Redis 超时**：

```bash
redis-cli INFO stats | grep -E "rejected_connections|blocked_clients"
redis-cli SLOWLOG GET 10
```

**外部 API 调用超时**：
- 检查应用日志中是否有 `timeout`、`connection refused`、`read timeout` 关键字
- 使用 `curl -v --max-time 5 <external_api_url>` 手动测试外部 API 响应

### 第三步：排查服务内部问题

**线程/协程池耗尽**：

```bash
# 查看 Python 进程的线程数
cat /proc/<PID>/status | grep Threads

# 查看端口连接状态
ss -tnp | grep <PORT> | awk '{print $1}' | sort | uniq -c
```

**GC 停顿（Java 服务）**：
- 检查 GC 日志：`grep -E "GC|pause" /path/to/gc.log | tail -50`
- GC 停顿超过 500ms 时，考虑调整 JVM 堆大小或切换 G1/ZGC 垃圾回收器

**事件循环阻塞（Node.js/Python asyncio）**：
- 检查是否有同步 IO 或 CPU 密集操作阻塞了事件循环
- 使用 `asyncio.get_event_loop().slow_callback_duration` 设置慢回调告警

### 第四步：临时缓解措施

**重启服务（最快恢复路径）**：

```bash
# 滚动重启，先重启非主力节点验证
systemctl restart <service_name>
# 或 Docker 场景
docker restart <container_name>
```

**限流保护**：
- 如果是流量突增导致，在 Nginx/API Gateway 层临时降低限流阈值
- 触发熔断，对下游不健康服务返回降级响应

**扩容**：
- 快速扩容副本数（K8s 场景）：`kubectl scale deployment/<name> --replicas=<n>`

### 第五步：根因分析与永久修复

- 采集故障时间段的链路追踪数据（Jaeger/Zipkin），找出最慢的 Span
- 提交性能优化工单，关联延迟趋势截图和慢查询日志
- 评估是否需要加索引、优化 SQL、引入缓存层或异步化处理
- 设置合理的超时配置（连接超时、读超时、重试次数）

## 升级路径

| 延迟 / 错误率 | 操作 |
|---------------|------|
| P99 2s–5s | 排查依赖，通知业务负责人 |
| P99 > 5s 或错误率 > 5% | 启动应急，考虑降级或重启 |
| 服务完全不可用 | 切换备用节点，拉起跨团队应急群 |

## 相关文档

- Prometheus 告警规则：`prometheus/alert_rules.yml`
- 数据库慢查询优化手册：`runbook_slow_query.md`
- 链路追踪接入文档：`docs/tracing.md`
- 高 CPU 使用率处理手册：`runbook_high_cpu.md`
