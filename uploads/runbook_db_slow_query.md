# 数据库慢查询处理

> 最后更新：2024-11-20 | 维护人：数据库组 @wangfang

慢查询告警触发时先别急着重启，大多数情况是索引问题或者锁等待，重启只是暂时掩盖。

---

## 告警来源

Prometheus 告警：`MySQLSlowQueryRate`
```
mysql_global_status_slow_queries rate > 10 for 5m
```

也可能是应用侧 APM 上报的 P99 延迟超阈值。两种来源处理方式不同，见下。

---

## 先看当前在跑什么

```sql
SHOW FULL PROCESSLIST;
```

重点看 `Time` 列超过 5 秒的，`State` 列能告诉你卡在哪：

| State | 含义 |
|-------|------|
| `Waiting for table lock` | 表锁争抢，找持锁者 |
| `Copying to tmp table` | filesort 或大 GROUP BY，看执行计划 |
| `Sending data` | 可能扫全表，也可能网络慢 |
| `Locked` | 行锁等待，看 innodb status |

---

## 找具体慢 SQL

**方法一：实时慢查询日志**（需要先确认已开启）
```sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
-- 日志位置：
SHOW VARIABLES LIKE 'slow_query_log_file';
```

```bash
# 尾追慢查询日志
tail -f /var/lib/mysql/slow.log

# 用 pt-query-digest 聚合分析（已安装在 db-tools 节点）
pt-query-digest /var/lib/mysql/slow.log --since 1h --limit 10
```

**方法二：performance_schema**（线上推荐，不需要开慢查询日志）
```sql
SELECT
  digest_text,
  count_star,
  avg_timer_wait / 1e12 AS avg_seconds,
  sum_rows_examined / count_star AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE avg_timer_wait > 5e12  -- 5秒
ORDER BY avg_timer_wait DESC
LIMIT 20;
```

---

## 拿到 SQL 之后

```sql
EXPLAIN SELECT ...;
-- 或者更详细的：
EXPLAIN ANALYZE SELECT ...;  -- MySQL 8.0+
```

关注点：
- `type` 列：`ALL` = 全表扫描，必须处理；`index` = 索引扫描，看情况
- `rows` 列：预估扫描行数，超过 100w 要警惕
- `Extra` 列：`Using filesort` 和 `Using temporary` 是性能杀手

**示例输出（问题 case）：**
```
+----+-------------+-------+------+---------------+------+---------+------+---------+-------------+
| id | select_type | table | type | possible_keys | key  | key_len | ref  | rows    | Extra       |
+----+-------------+-------+------+---------------+------+---------+------+---------+-------------+
|  1 | SIMPLE      | order | ALL  | NULL          | NULL | NULL    | NULL | 3847291 | Using where |
+----+-------------+-------+------+---------------+------+---------+------+---------+-------------+
```
rows=384万，type=ALL，没命中任何索引 → 加索引。

---

## 是锁的问题

```sql
-- 查看锁等待
SELECT * FROM information_schema.INNODB_LOCK_WAITS;

-- 找持锁线程
SELECT r.trx_id waiting_trx_id,
       r.trx_mysql_thread_id waiting_thread,
       b.trx_id blocking_trx_id,
       b.trx_mysql_thread_id blocking_thread,
       b.trx_query blocking_query
FROM information_schema.INNODB_TRX b
JOIN information_schema.INNODB_TRX r ON r.trx_wait_started IS NOT NULL
JOIN information_schema.INNODB_LOCK_WAITS w ON w.requesting_trx_id = r.trx_id
  AND w.blocking_trx_id = b.trx_id;
```

如果持锁线程的 `blocking_query` 是 NULL，说明事务已提交但未释放，或者是一个长事务在 idle 状态。
可以 `KILL <blocking_thread>` 释放锁，但要先确认影响范围（跟业务侧确认）。

---

## 临时缓解

情况太紧、来不及加索引时：

1. 限速：在应用侧或网关加查询频率限制（联系平台组）
2. 读写分离：把问题查询临时导到只读副本
3. Kill 掉积压的慢查询（会导致事务回滚，跟业务确认）

```sql
-- 批量 kill 超过 30 秒的查询（谨慎使用）
SELECT CONCAT('KILL ', id, ';')
FROM information_schema.PROCESSLIST
WHERE TIME > 30 AND USER != 'replication';
```

---

## 根因处理

| 根因 | 处理 |
|------|------|
| 缺少索引 | 先评估索引代价（写入频率），开发确认后执行 `ALTER TABLE ... ADD INDEX` |
| 统计信息过期 | `ANALYZE TABLE <table_name>` |
| SQL 写法问题 | 联系开发优化，参考《SQL 编写规范》wiki |
| 数据量增长超预期 | 评估归档或分表，找 DBA 排期 |

---

*相关文档：reference_prometheus_metrics.md / 《SQL 编写规范》内网 wiki*
