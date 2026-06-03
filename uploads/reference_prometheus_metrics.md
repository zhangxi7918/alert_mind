# Prometheus 监控指标参考手册

本文档描述系统中各核心监控指标的含义、正常范围和告警阈值，供运维人员日常巡检和告警响应时参考。

## CPU 相关指标

### node_cpu_seconds_total

**类型：** Counter
**含义：** 自节点启动以来各模式（user/system/idle/iowait/irq 等）累计消耗的 CPU 时间（秒）
**常用查询：**

```promql
# 最近 5 分钟 CPU 使用率（所有核平均）
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 按核分布（排查是否单核跑满）
100 - (avg by(instance, cpu) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# iowait 占比（高 iowait 表示 IO 等待，不一定是 CPU 计算瓶颈）
avg by(instance) (rate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100
```

**告警阈值：**

| 级别 | 阈值 | 持续时间 |
|------|------|----------|
| Warning | > 80% | 1 分钟 |
| Critical | > 95% | 30 秒 |

**注意：** iowait 高不等于 CPU 瓶颈，需结合磁盘 IO 指标综合判断。

---

### process_cpu_seconds_total

**类型：** Counter
**含义：** 单个进程累计消耗的 CPU 时间（秒）
**常用查询：**

```promql
# 单进程 CPU 使用率
rate(process_cpu_seconds_total{job="alert-mind-agent"}[5m]) * 100
```

---

## 内存相关指标

### node_memory_MemAvailable_bytes

**类型：** Gauge
**含义：** 当前可用内存字节数（包含 buffer/cache 可回收部分）
**常用查询：**

```promql
# 可用内存百分比
(node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100

# 已用内存量（GB）
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / 1024 / 1024 / 1024
```

**告警阈值：**

| 级别 | 阈值 | 说明 |
|------|------|------|
| Warning | 可用内存 < 20% | 开始关注内存压力 |
| Critical | 可用内存 < 10% | 存在 OOM Kill 风险 |

---

### node_memory_SwapUsed_bytes

**类型：** Gauge（通过 Total - Free 计算）
**含义：** 当前 Swap 使用量
**常用查询：**

```promql
node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes
```

**说明：** 生产环境 Swap 使用量持续增长，通常意味着内存不足，需要关注实际内存使用。

---

## 磁盘相关指标

### node_filesystem_avail_bytes

**类型：** Gauge
**含义：** 文件系统可用空间（非 root 用户可用）
**常用查询：**

```promql
# 各挂载点可用空间百分比
(node_filesystem_avail_bytes{fstype!~"tmpfs|devtmpfs"} 
  / node_filesystem_size_bytes{fstype!~"tmpfs|devtmpfs"}) * 100

# 磁盘使用率超过 80% 的挂载点
(1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 > 80
```

**告警阈值：**

| 级别 | 阈值 |
|------|------|
| Warning | 使用率 > 80% |
| Critical | 使用率 > 90% |

---

### node_disk_io_time_seconds_total

**类型：** Counter
**含义：** 磁盘 IO 操作总耗时（秒）
**常用查询：**

```promql
# 磁盘 IO 繁忙度（接近 1 表示磁盘接近饱和）
rate(node_disk_io_time_seconds_total[5m])
```

---

## 网络相关指标

### node_network_receive_bytes_total / node_network_transmit_bytes_total

**类型：** Counter
**常用查询：**

```promql
# 接口接收速率（MB/s）
rate(node_network_receive_bytes_total{device="eth0"}[5m]) / 1024 / 1024

# 接口发送速率（MB/s）
rate(node_network_transmit_bytes_total{device="eth0"}[5m]) / 1024 / 1024
```

---

### node_network_receive_errs_total

**类型：** Counter
**含义：** 网络接收错误包数
**说明：** 持续增长表明网络硬件故障或信号问题，需检查网卡和交换机。

---

## HTTP 服务相关指标

### http_request_duration_seconds

**类型：** Histogram
**含义：** HTTP 请求处理时间分布
**常用查询：**

```promql
# P99 响应时间
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# P95 响应时间
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# 请求错误率（5xx）
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
```

**告警阈值：**

| 指标 | 级别 | 阈值 |
|------|------|------|
| P99 响应时间 | Warning | > 500ms |
| P99 响应时间 | Critical | > 2s |
| 错误率 | Warning | > 1% |
| 错误率 | Critical | > 5% |

---

## 数据库连接池指标

### db_connection_pool_size / db_connection_pool_checked_out

**类型：** Gauge（应用自定义指标）
**含义：** 连接池总大小 / 当前已签出连接数
**常用查询：**

```promql
# 连接池使用率
db_connection_pool_checked_out / db_connection_pool_size * 100
```

**告警阈值：** 使用率 > 90% 触发 DBConnectionPoolExhausted 告警。

---

## 巡检建议

日常巡检时，建议按优先级检查：

1. CPU 使用率趋势（重点关注持续增长）
2. 可用内存和 Swap 使用情况
3. 磁盘使用率（尤其是 `/var` 和日志挂载点）
4. 网络错误包统计（是否有持续增长）
5. 数据库连接池使用率

每周输出一次各指标基线报告，用于识别异常波动。
