# 高 CPU 使用率处理手册

## 告警说明

告警名称：HighCPUUsage
触发条件：CPU 使用率持续 1 分钟超过 80%
严重等级：Warning
负责团队：基础设施运维组

## 排查步骤

### 第一步：确认告警真实性

通过 Prometheus 查询当前 CPU 使用率，排除采集抖动：

```
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

如果 CPU 使用率低于 70%，视为误告警，标记为已解决并记录原因。

### 第二步：定位高 CPU 进程

登录目标主机，执行以下命令找出占用 CPU 最高的进程：

```bash
# 查看 CPU 占用 Top 10 进程
top -bn1 | head -20

# 或使用 ps 排序
ps aux --sort=-%cpu | head -15

# Docker 容器场景下查看各容器 CPU
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### 第三步：分析进程类型

**场景 A：业务进程（Python/Java/Node）占用过高**
- 检查近期是否有代码发布或配置变更
- 查看应用日志是否有死循环、递归或大量异常堆栈
- 使用 `strace -p <PID>` 或 JVM 的 `jstack` 分析线程状态

**场景 B：系统进程（kworker/systemd/cron）占用过高**
- 检查是否有计划任务在运行：`crontab -l` 和 `systemctl list-timers`
- 内核更新或磁盘 IO 高峰可能触发 kworker 飙升，需结合磁盘监控排查

**场景 C：Docker 容器 CPU 暴涨**
- 确认是哪个容器：`docker stats`
- 进入容器排查：`docker exec -it <container_name> top`
- 检查容器是否设置了 CPU 限制，考虑临时限流：`docker update --cpus="1.5" <container_name>`

### 第四步：临时缓解措施

如果业务受影响，需立即降低 CPU 压力：

```bash
# 降低进程优先级（不杀进程）
renice 10 -p <PID>

# 限制进程 CPU 使用（需安装 cpulimit）
cpulimit -p <PID> -l 50

# 如果是非关键进程，可临时暂停
kill -STOP <PID>
# 恢复：kill -CONT <PID>
```

### 第五步：根因分析与永久修复

- 记录告警触发时间、持续时长、影响范围
- 提交问题工单，关联 Prometheus 告警截图
- 与研发团队确认是否需要代码优化、扩容或调整限流策略
- 在 CMDB 中更新配置项的 CPU 基线值

## 升级路径

| 持续时长 | 操作 |
|----------|------|
| < 5 分钟 | 观察，记录日志 |
| 5–15 分钟 | 执行上述排查，通知业务负责人 |
| > 15 分钟 | 启动应急响应，拉起跨团队群，考虑服务降级或扩容 |

## 相关文档

- Prometheus 告警规则：`prometheus/alert_rules.yml`
- 扩容操作手册：`runbook_scaling.md`
- 磁盘 IO 高排查手册：`runbook_disk_io.md`
