# Kafka 生产者发送失败处理

**告警**：`KafkaProducerErrorRateHigh` / 应用日志 `Failed to send message` / `TimeoutException` / `NotLeaderForPartitionException`

_注意：这是生产者侧问题，消费者积压问题见 runbook_kafka_consumer_lag.pdf_

---

## 快速判断错误类型

先从应用日志里找具体的异常：

```bash
kubectl logs <pod> -n <ns> --tail=200 | grep -E "KafkaException|TimeoutException|ProducerFenced|AuthorizationException"
```

| 异常 | 方向 |
|------|------|
| `TimeoutException: Expiring X record(s)` | 发送超时，Broker 慢或网络问题 |
| `NotLeaderForPartitionException` | Partition leader 正在切换，短暂性，通常自愈 |
| `RecordTooLargeException` | 消息体超过 `max.message.bytes`，是配置/代码问题 |
| `AuthorizationException` | ACL 权限问题 |
| `ProducerFencedException` | 幂等/事务 producer 被 fence，严重，数据可能不一致 |

---

## 发送超时（最常见）

**第一步：看 Broker 健康状态**

```bash
# 检查 Kafka Broker Pod
kubectl get pods -n kafka -l app=kafka

# 看 Broker 日志
kubectl logs -n kafka kafka-0 --tail=100 | grep -E "ERROR|WARN"
```

**第二步：看网络和连接**

```bash
# 在应用 Pod 里测试到 Kafka 的连通性
kubectl exec -it <app-pod> -n <ns> -- nc -zv kafka-0.kafka.svc.cluster.local 9092
kubectl exec -it <app-pod> -n <ns> -- nc -zv kafka-1.kafka.svc.cluster.local 9092
```

**第三步：看生产者指标**

```promql
# 生产者请求延迟 P99
kafka_producer_request_latency_avg{client_id="..."}

# 重试率
rate(kafka_producer_record_retry_total[5m])

# 发送失败率
rate(kafka_producer_record_error_total[5m])
```

**缓解方案**：如果是瞬时抖动，增加 producer 的 `retries` 和 `retry.backoff.ms` 可以吸收；如果是持续性问题，需要先减少发送频率（在应用侧限速）。

---

## Partition Leader 切换

`NotLeaderForPartitionException` 通常在 Broker 重启或网络分区时出现，producer 会自动 refresh metadata 并重试，**不需要人工介入**。

如果持续出现超过 5 分钟：
```bash
# 检查 Partition 分布是否均匀
kubectl exec -it kafka-0 -n kafka -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic <topic-name>

# 触发 preferred leader election（如果 leader 分布不均匀）
kubectl exec -it kafka-0 -n kafka -- kafka-leader-election.sh \
  --bootstrap-server localhost:9092 \
  --election-type PREFERRED \
  --topic <topic-name>
```

---

## 消息体过大

`RecordTooLargeException` 是代码/配置问题，不是基础设施问题。

选择一：修改 Broker 和 Producer 的 `max.message.bytes` 限制（需要评估影响）
选择二：让开发团队拆分消息或压缩消息体

---

## 生产者事务问题（ProducerFencedException）

这个异常表示有另一个 producer 实例用相同的 `transactional.id` 启动了，导致旧实例被 fence。

常见原因：滚动发布时新旧实例并存，使用了相同的 `transactional.id`。

**立即确认数据完整性**（优先于恢复）：
- 检查下游 topic 是否有重复或丢失消息
- 通知业务侧暂停对该 topic 的消费，等确认后再恢复

不要在没理清楚影响前就重启生产者。重启会产生新的 transaction epoch，未提交的事务会被 abort，数据可能不一致。

---

## 升级条件

- 生产者错误率持续 > 5%，超过 10 分钟 → P1
- `ProducerFencedException` 出现 → 立即 P1，通知数据团队
- 核心业务数据写入失败（支付/订单） → P0

*相关：参考 reference_prometheus_metrics.md 中 Kafka 相关指标定义*
