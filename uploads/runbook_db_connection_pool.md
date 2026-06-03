# 数据库连接池耗尽处理手册

## 告警说明

告警名称：DBConnectionPoolExhausted
触发条件：数据库连接池使用率超过 90% 持续 1 分钟，或出现 "too many connections" 错误
严重等级：Critical
负责团队：基础设施运维组 / 数据库管理员

## 排查步骤

### 第一步：确认当前连接状态

**MySQL：**

```sql
-- 查看当前连接数
SHOW STATUS LIKE 'Threads_connected';

-- 查看最大连接数配置
SHOW VARIABLES LIKE 'max_connections';

-- 查看各客户端 IP 的连接数分布
SELECT host, count(*) FROM information_schema.processlist GROUP BY host ORDER BY count(*) DESC;

-- 查看当前活跃的慢查询
SHOW PROCESSLIST;
-- 或查看超过 10 秒的长事务
SELECT * FROM information_schema.processlist WHERE time > 10 ORDER BY time DESC;
```

**PostgreSQL：**

```sql
-- 查看当前连接数
SELECT count(*) FROM pg_stat_activity;

-- 查看各状态连接分布
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- 查看长事务（超过 5 分钟）
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes';
```

### 第二步：定位连接泄漏

连接池耗尽的主要原因是连接使用后未正确释放：

```bash
# 查看应用层连接池状态（以 Python SQLAlchemy 为例，需在应用暴露 metrics）
curl http://localhost:9000/metrics | grep -i "connection_pool"

# 查看 TCP 连接状态分布
ss -tn | awk '{print $1}' | sort | uniq -c
netstat -an | grep 3306 | awk '{print $6}' | sort | uniq -c
```

**CLOSE_WAIT 连接过多**是连接泄漏的典型症状，表示应用端没有正常关闭连接。

### 第三步：排查慢查询积压

慢查询会长时间占用连接，导致连接池被耗尽：

```sql
-- MySQL：开启慢查询日志后查看
SHOW VARIABLES LIKE 'slow_query_log%';
SHOW VARIABLES LIKE 'long_query_time';

-- 查看当前执行时间最长的查询
SELECT * FROM information_schema.processlist
WHERE command != 'Sleep'
ORDER BY time DESC LIMIT 10;
```

### 第四步：排查连接池配置

检查应用层连接池参数设置是否合理：

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| pool_size | 连接池基础大小 | CPU 核数 × 2 |
| max_overflow | 超出基础大小后允许创建的额外连接数 | pool_size × 0.5 |
| pool_timeout | 等待获取连接的超时时间（秒） | 30 |
| pool_recycle | 连接最大复用时间（秒），防止使用断开的陈旧连接 | 1800 |

## 临时缓解措施

**紧急扩大 MySQL 最大连接数（临时）：**

```sql
-- 临时提升（重启后失效）
SET GLOBAL max_connections = 500;
```

**强制关闭空闲时间过长的连接：**

```sql
-- 找出空闲超过 300 秒的连接
SELECT concat('KILL ', id, ';')
FROM information_schema.processlist
WHERE command = 'Sleep' AND time > 300;
-- 将输出的 KILL 语句逐条执行
```

**重启应用服务（最快速方案，连接会被全部释放）：**

```bash
docker restart <app_container_name>
```

## 根因分类与永久修复

| 根因 | 修复方案 |
|------|----------|
| 连接未释放（代码 bug） | 检查 ORM 事务是否有 finally/with 语句保证关闭 |
| 慢查询积压 | 优化索引，增加查询超时限制 |
| 连接池配置过小 | 调大 pool_size，或引入 PgBouncer/ProxySQL 连接代理 |
| 流量突增 | 评估扩容数据库实例或开启读写分离 |

## 升级路径

| 状态 | 操作 |
|------|------|
| 连接使用率 90-95% | 通知 DBA，开始排查，准备重启应用 |
| 连接使用率 > 95%，业务报错 | 立即重启应用服务释放连接，同时排查根因 |
| 数据库响应超时 | 启动 P1 应急响应，考虑切换备库 |

## 相关文档

- 服务超时排查手册：`runbook_service_timeout.md`
- 服务依赖拓扑：`reference_service_topology.md`
- Prometheus 指标参考：`reference_prometheus_metrics.md`
