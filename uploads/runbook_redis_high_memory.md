# Redis 内存压力处理手册

**告警**：`RedisMemoryUsageHigh`
**阈值**：内存使用率 > 85%（相对于 maxmemory 配置）

_注意：Redis 缓存雪崩是独立场景，见 runbook_redis_cache_avalanche.pdf_

---

## 先确认当前状态

```bash
# 连接 Redis
kubectl exec -it <redis-pod> -n <ns> -- redis-cli

# 查看内存详情
INFO memory
```

重点字段：

| 字段 | 含义 |
|------|------|
| `used_memory_human` | 实际使用内存 |
| `maxmemory_human` | 配置的内存上限 |
| `mem_fragmentation_ratio` | 内存碎片率，正常 1.0-1.5，>1.5 说明碎片严重 |
| `evicted_keys` | 被驱逐的 key 数量，不为 0 说明 maxmemory 不够用了 |
| `maxmemory_policy` | 驱逐策略 |

---

## 三种根因，处理方式不同

### 情况 A：数据量正常增长，内存不够用了

```bash
# 看 key 数量趋势
INFO keyspace

# 看各 DB 的 key 数量
redis-cli INFO keyspace | grep db
```

这是正常的容量问题。解法：

1. **短期**：调高 `maxmemory`（需要节点有足够物理内存）
   ```bash
   redis-cli CONFIG SET maxmemory 4gb
   # 同时更新配置文件，否则重启后失效
   ```

2. **中期**：设置合理的 TTL，避免 key 永久存在
   ```bash
   # 找没有 TTL 的大 key（谨慎，scan 有性能开销）
   redis-cli --scan --pattern '*' | xargs -I{} redis-cli object encoding {}
   ```

3. **长期**：评估是否需要扩容或 Redis Cluster 分片

### 情况 B：内存碎片率高（mem_fragmentation_ratio > 1.5）

碎片是频繁删除/更新 key 导致的，内存实际可用但碎片化无法被利用。

```bash
# Redis 4.0+ 支持在线碎片整理（有性能开销，在低峰期执行）
redis-cli CONFIG SET activedefrag yes
redis-cli CONFIG SET active-defrag-ignore-bytes 100mb
redis-cli CONFIG SET active-defrag-threshold-lower 10
```

整理期间注意观察 CPU 使用率，如果压力大及时关闭：
```bash
redis-cli CONFIG SET activedefrag no
```

### 情况 C：有大 key 或热点 key 异常增长

```bash
# 找 top 大 key（Redis 4.0+）
redis-cli --memkeys --memkeys-samples 100

# 或者用 redis-cli 的 bigkeys 扫描
redis-cli --bigkeys

# 检查特定 key 的大小
redis-cli DEBUG OBJECT <key-name>
# 看 serializedlength 字段
```

大 key 常见于：无边界的 List/Set 持续 push 但没有消费、缓存了完整的大数据集、Session 数据未清理。

联系对应业务团队，确认是否有 bug（无限增长）还是预期行为（需要调整策略）。

---

## 驱逐策略参考

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `noeviction` | 内存满时拒绝写入（报错） | 数据不能丢失的场景 |
| `allkeys-lru` | 驱逐最近最少使用的 key | 纯缓存场景（推荐） |
| `allkeys-lfu` | 驱逐访问频率最低的 key | 访问模式不均匀时比 LRU 更好 |
| `volatile-lru` | 只驱逐有 TTL 的 key（LRU） | 混合存储（缓存+持久化数据） |
| `volatile-ttl` | 优先驱逐 TTL 最短的 key | 希望先清过期数据 |

当前策略查看：
```bash
redis-cli CONFIG GET maxmemory-policy
```

---

## 升级路径

| 内存使用率 | 操作 |
|----------|------|
| 85-90% | 告警响应，分析根因，制定计划 |
| 90-95% | 开始执行缓解措施（碎片整理/驱逐策略调整） |
| > 95% | 立即临时扩内存或触发 noeviction 下的报错保护 |
| evicted_keys 快速增长 | 说明驱逐压力大，数据可能丢失，立即升级 P1 |
