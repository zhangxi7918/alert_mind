# 告警规则配置说明

本文档说明 alert_mind 平台的 Prometheus 告警规则设计原则、分级标准和各规则的配置逻辑，供运维人员理解告警意图和调整阈值时参考。

## 告警分级标准

| 级别 | 颜色 | 含义 | 响应时限 |
|------|------|------|----------|
| Info | 蓝色 | 信息性通知，无需立即处理 | 下一个工作日 |
| Warning | 黄色 | 潜在问题，需关注，业务暂无影响 | 30 分钟内响应 |
| Critical | 红色 | 业务受影响或即将受影响，需立即处理 | 5 分钟内响应 |
| Emergency | 紫色 | 业务中断，最高优先级 | 立即响应 |

---

## CPU 告警规则

### HighCPUUsage

```yaml
alert: HighCPUUsage
expr: >
  100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
for: 1m
labels:
  severity: warning
annotations:
  summary: "主机 {{ $labels.instance }} CPU 使用率过高"
  description: "CPU 使用率为 {{ $value | printf \"%.1f\" }}%，已持续超过 1 分钟"
  runbook: "runbook_high_cpu.md"
```

**设计说明：**
- `for: 1m` 避免采集抖动产生误报（瞬间毛刺不触发）
- 使用 `avg by(instance)` 避免单核满但整体不高的误报
- 阈值 80% 是经验值，内存密集型应用可适当调高到 85%

---

### HighCPUUsageCritical

```yaml
alert: HighCPUUsageCritical
expr: >
  100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 95
for: 30s
labels:
  severity: critical
```

**说明：** 95% 以上说明系统接近饱和，`for: 30s` 更短以加快响应速度。

---

## 内存告警规则

### LowMemoryAvailable

```yaml
alert: LowMemoryAvailable
expr: >
  (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 < 20
for: 2m
labels:
  severity: warning
annotations:
  runbook: "runbook_high_memory.md"
```

### HighMemoryUsage（等价写法）

```yaml
alert: HighMemoryUsage
expr: >
  (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 80
for: 2m
labels:
  severity: warning
```

**说明：** 两个规则本质相同，选其一即可，避免同时触发重复告警。

---

## 磁盘告警规则

### DiskSpaceLow

```yaml
alert: DiskSpaceLow
expr: >
  (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|devtmpfs"} 
     / node_filesystem_size_bytes{fstype!~"tmpfs|devtmpfs"}) * 100 > 80
for: 5m
labels:
  severity: warning
annotations:
  runbook: "runbook_disk_space.md"
```

### DiskSpaceCritical

```yaml
alert: DiskSpaceCritical
expr: >
  (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|devtmpfs"} 
     / node_filesystem_size_bytes{fstype!~"tmpfs|devtmpfs"}) * 100 > 90
for: 2m
labels:
  severity: critical
```

**说明：**
- `fstype!~"tmpfs|devtmpfs"` 过滤内存文件系统，避免无意义告警
- 磁盘使用率通常增长较慢，`for: 5m` 避免大文件临时写入产生误报

---

## 网络告警规则

### HighNetworkLatency

```yaml
alert: HighNetworkLatency
expr: >
  histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 0.2
for: 2m
labels:
  severity: warning
annotations:
  runbook: "runbook_network_latency.md"
```

### NetworkErrors

```yaml
alert: NetworkErrors
expr: >
  rate(node_network_receive_errs_total[5m]) > 10
for: 1m
labels:
  severity: warning
```

---

## 容器告警规则

### ContainerRestartLoop

```yaml
alert: ContainerRestartLoop
expr: >
  increase(container_restart_count[30m]) > 3
for: 0m
labels:
  severity: warning
annotations:
  runbook: "runbook_container_restart.md"
```

**说明：** `for: 0m` 表示一旦满足条件立即触发，不等待持续时长，因为容器重启本身就是异常事件。

---

## 数据库告警规则

### DBConnectionPoolExhausted

```yaml
alert: DBConnectionPoolExhausted
expr: >
  db_connection_pool_checked_out / db_connection_pool_size * 100 > 90
for: 1m
labels:
  severity: critical
annotations:
  runbook: "runbook_db_connection_pool.md"
```

---

## 告警抑制规则

当高级别告警触发时，抑制同一实例的低级别告警，避免告警风暴：

```yaml
inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal:
      - instance
```

---

## 告警分组与路由

```yaml
route:
  group_by: ['alertname', 'instance']
  group_wait: 30s        # 等待 30s 聚合同一批次告警
  group_interval: 5m     # 同一分组后续通知间隔
  repeat_interval: 4h    # 持续告警的重复通知间隔
  receiver: default

receivers:
  - name: default
    # 配置钉钉/企业微信/邮件等通知渠道
```

**group_wait 说明：** 30 秒的等待允许同一时间触发的多个相关告警合并为一条通知，减少告警疲劳。

---

## 阈值调整指南

调整告警阈值前，建议：

1. 收集历史 2 周的指标数据，了解正常业务峰值
2. 阈值设置在峰值以上 20% 的位置作为 Warning 起点
3. Critical 阈值设置在 Warning 的 1.2-1.5 倍
4. 调整后在非业务高峰时段观察 1 周，确认误报率降低

切忌为了减少告警而持续调高阈值，这会导致真正的问题被掩盖。
