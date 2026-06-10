# 内存泄漏排查

**告警**：`ContainerMemoryUsageHigh`（容器内存持续增长，未随负载降低而回落）

内存泄漏和内存使用高是两件事。使用高不等于泄漏。区分方法：重启后能不能恢复、内存增长是否跟负载相关。

---

## 是真的泄漏吗？

```
内存在持续增长？
├── 是 → 重启服务后恢复了吗？
│         ├── 是 → 大概率是泄漏，继续排查
│         └── 否 → 可能是外部原因（节点内存压力、cgroup 限制），换一个节点验证
└── 否 → 内存高但稳定？
          ├── 跟流量正相关 → 正常，考虑调整 requests/limits
          └── 跟流量无关 → 可能是缓存未设上限，检查应用缓存配置
```

---

## JVM 应用（Java/Kotlin/Scala）

```bash
# 先看 GC 情况
kubectl exec -it <pod> -n <ns> -- jstat -gcutil 1 1000 10
# S0/S1/E/O/M 分别是幸存区/Eden/老年代/元空间占用率
# 关注 O（老年代）：持续增长且 FGC 后不下降 → 老年代泄漏
```

```bash
# 打 heap dump（需要容器内有 jmap，或者用 jattach）
kubectl exec -it <pod> -n <ns> -- jmap -dump:format=b,file=/tmp/heap.hprof <pid>

# 把 dump 文件拷出来
kubectl cp <ns>/<pod>:/tmp/heap.hprof ./heap.hprof
```

用 Eclipse MAT 或 VisualVM 分析 heap.hprof，重点看：
- Leak Suspects Report（MAT 自动分析）
- 占用最多内存的对象类型
- 引用链（谁持有这些对象导致 GC 无法回收）

常见泄漏模式：
- 静态集合（`static Map/List`）无限增长
- 监听器/回调注册了但没注销
- 线程本地变量（ThreadLocal）未 remove
- 连接/流未关闭

---

## Go 应用

```bash
# 开启 pprof（如果应用没开，需要发版）
kubectl port-forward pod/<pod> 6060:6060 -n <ns>

# 采样 heap profile（30秒）
go tool pprof http://localhost:6060/debug/pprof/heap

# 采样 goroutine（检查 goroutine 泄漏）
curl http://localhost:6060/debug/pprof/goroutine?debug=1 | head -50
```

Goroutine 泄漏是 Go 应用内存泄漏的常见原因，表现为 goroutine 数量持续增长而不释放。

```bash
# 看 goroutine 数量趋势（如果有 Prometheus 指标）
go_goroutines{pod="..."}
```

---

## 容器层面兜底

如果泄漏短期无法修复，可以配置自动重启作为临时措施：

```yaml
# 在 Pod spec 中加 liveness probe（已有可跳过）
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3

# 或者直接设内存限制，OOM 后 k8s 会自动重启
resources:
  limits:
    memory: "2Gi"
```

OOM 重启是一个应急手段，不是解法。需要跟开发团队同步，安排时间定位根因。

---

## 升级判断

| 场景 | 操作 |
|------|------|
| 内存增长慢，有时间排查 | 按上述步骤排查，开发修复 |
| 内存接近 limit，有 OOM 风险 | 临时扩大 limit + 通知开发紧急处理 |
| 已经 OOM Killed 影响服务 | 判断为事故，升级处理，同时配置重启策略兜底 |
