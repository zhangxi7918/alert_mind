# Grafana 监控看板使用指南

_本文档说明各监控看板的用途和关键指标解读方法。看板地址见内网文档（不在此列出）。_

---

## 看板总览

我们有三层看板，按告警处理顺序使用：

**第一层：全局健康看板（Golden Signals Overview）**
快速判断哪个服务有问题。告警响应第一步先看这里。

**第二层：服务级看板（Service Dashboard）**
每个核心服务一个，包含该服务的完整指标。定位到服务后进入这层。

**第三层：基础设施看板（Infrastructure）**
节点、Pod、网络、存储的底层指标。怀疑是资源层问题时进入这层。

---

## 全局健康看板怎么用

看板按 Google SRE 的四个黄金信号组织：**流量（Traffic）、延迟（Latency）、错误（Errors）、饱和度（Saturation）**。

**流量面板**：看各服务的 QPS 趋势。有告警时，先确认流量是否异常（突增或骤降都是信号）。QPS 骤降有时比骤增更危险——可能是服务不可用导致请求进不来，不是流量真的少了。

**延迟面板**：P99 延迟是主要观测指标，不要看平均值（平均值会被少量快请求拉低，掩盖问题）。P99 超过 SLO 定义阈值时需要处理。

**错误率面板**：5xx 错误率按服务分组显示。颜色是 traffic light 系统：绿色 < 0.1%，黄色 0.1-1%，红色 > 1%。

**饱和度面板**：CPU 和内存水位热力图。颜色越深说明资源越紧张。

---

## 时间范围选择技巧

告警响应时：先选 **Last 1 hour**，定位告警开始时间；然后缩小到 **Last 15 minutes** 看细节；如果需要对比历史同期，用 **Compare** 功能选择上周同时段。

注意：Prometheus 默认保留 15 天数据，更长期的历史数据在 Thanos 里（查询稍慢）。切换方法：数据源下拉选 "Thanos"。

---

## 关键面板解读

### API 网关面板

| 面板名称 | 指标 | 异常阈值 |
|---------|------|---------|
| Request Rate | `nginx_http_requests_total` rate | 比日常 > 3x 需关注 |
| Error Rate | 5xx 占比 | > 1% 需处理 |
| P99 Latency | `nginx_request_duration_seconds` p99 | > 500ms 需关注 |
| Upstream Response Time | 上游响应时间 | > 300ms 需排查上游 |
| Active Connections | 当前连接数 | 接近 max_conns 需扩容 |

### 数据库面板

慢查询率（`mysql_global_status_slow_queries` rate）是最重要的指标，正常情况应该接近 0。

QPS 面板会区分读写，写 QPS 突增通常跟业务活动相关，读 QPS 突增可能是缓存失效。

Replication lag（主从延迟）超过 30 秒需要关注，超过 5 分钟需要处理。

### 缓存（Redis）面板

命中率（Hit Rate）正常应该在 90% 以上，突然下降说明缓存大量失效（可能是缓存雪崩）。

内存使用率接近 `maxmemory` 时，Redis 会触发 eviction，可能导致命中率下降。

---

## 常用 Prometheus 查询

自定义查询时可以直接在 Grafana 的 "Explore" 模式输入：

```promql
# 某服务过去 5 分钟错误率
sum(rate(http_requests_total{service="user-service",status=~"5.."}[5m]))
/ sum(rate(http_requests_total{service="user-service"}[5m]))

# Pod 内存使用率（相对 limit）
container_memory_working_set_bytes{pod=~"api-.*"}
/ container_spec_memory_limit_bytes{pod=~"api-.*"}

# 节点 CPU 使用率
1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))
```

---

## 设置临时告警静默

处理告警期间，如果已知某个告警是预期行为（如维护操作导致），可以在 Alertmanager 里设置 silence，避免干扰：

Alertmanager UI → New Silence → 填写 matcher（服务名/告警名）→ 设置持续时间 → 写明原因（必填）

**Silence 最长设置 4 小时**，超时需要重新设置。不要设置超过 24 小时的 silence——超长 silence 经常被遗忘，导致真实告警被压制。

---

*相关：reference_prometheus_metrics.md 有完整指标字典*
