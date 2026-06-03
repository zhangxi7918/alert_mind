# 内存不足处理手册

## 告警说明

告警名称：HighMemoryUsage / LowMemoryAvailable
触发条件：可用内存低于总内存的 15%（或绝对值低于 512MB）
严重等级：Warning（可用 < 15%）/ Critical（可用 < 5%）
负责团队：基础设施运维组

## 排查步骤

### 第一步：确认内存使用现状

```bash
# 查看内存使用概览
free -h

# 查看详细内存信息
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Cached|Buffers|SwapUsed"
```

Prometheus 查询当前内存使用率：

```
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

注意区分 `MemFree` 和 `MemAvailable`：前者不含 cache/buffer，后者是操作系统实际可分配给进程的内存，告警应基于 `MemAvailable`。

### 第二步：定位内存占用进程

```bash
# 按内存排序查看 Top 进程
ps aux --sort=-%mem | head -15

# 查看各 Docker 容器内存占用
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# 查看进程实际物理内存占用（RSS）
smem -r -k | head -20
```

### 第三步：分析内存泄漏

**判断是否存在内存泄漏**：
- 使用 Prometheus 绘制内存使用趋势图，若内存持续线性增长且从不释放，通常为内存泄漏
- 对 Java 进程执行堆转储：`jmap -dump:format=b,file=/tmp/heap.hprof <PID>`
- 对 Python 进程可使用 `tracemalloc` 或 `memory_profiler` 分析

**判断是缓存/buffer 占用**：
- `Cached` 值大时，Linux 内核会在需要时自动释放页缓存，通常无需人工干预
- 若需立即释放缓存（谨慎操作）：`sync && echo 3 > /proc/sys/vm/drop_caches`

### 第四步：临时缓解措施

**方案 A：重启占用最多内存的非关键服务**

```bash
# 确认服务名称后重启
systemctl restart <service_name>
# 或对 Docker 容器
docker restart <container_name>
```

**方案 B：检查并清理 Swap**

```bash
# 查看 Swap 使用情况
swapon --show
free -h

# 如果 Swap 使用率高，说明内存已严重不足，需立即扩容或缩减负载
```

**方案 C：限制容器内存上限（防止单容器吃尽内存）**

```bash
docker update --memory="2g" --memory-swap="2g" <container_name>
```

### 第五步：根因分析与永久修复

- 确认是突发流量导致（短期压力）还是持续增长（内存泄漏）
- 突发流量：评估是否需要水平扩容，增加节点数量
- 内存泄漏：提交 Bug 工单，关联 heap dump 或内存趋势截图，与研发排期修复
- 审查 JVM 参数（`-Xmx`）或 Python 进程的内存上限配置是否合理

## 升级路径

| 可用内存 | 操作 |
|----------|------|
| 15%–20% | 观察趋势，预警通知 |
| 5%–15% | 执行排查，通知业务负责人，准备重启方案 |
| < 5% | 立即启动应急响应，执行缓解措施，防止 OOM Kill |

## OOM Kill 处置

当内核触发 OOM Killer 终止进程时：

```bash
# 查看 OOM Kill 日志
dmesg | grep -i "oom\|killed process" | tail -20
journalctl -k | grep -i oom | tail -20
```

记录被杀进程的 PID 和名称，评估是否影响核心服务，按需执行服务恢复流程。

## 相关文档

- Prometheus 告警规则：`prometheus/alert_rules.yml`
- 扩容操作手册：`runbook_scaling.md`
- CPU 使用率高排查手册：`runbook_high_cpu.md`
