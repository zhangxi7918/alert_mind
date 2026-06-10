# 网关 5xx 率飙升 FAQ

**告警名**：`GatewayErrorRateHigh`
**阈值**：HTTP 5xx 占比 > 1% 持续 2 分钟

---

**Q：收到告警第一件事做什么？**

先看错误率趋势，判断是尖刺还是持续攀升：

```promql
sum(rate(nginx_http_requests_total{status=~"5.."}[1m])) /
sum(rate(nginx_http_requests_total[1m]))
```

尖刺（<30s）通常是单次发布或个别节点抖动，可以先观察。持续攀升必须立即处理。

---

**Q：怎么知道是哪个服务在报错？**

按 upstream 分组看：
```promql
sum by (upstream) (rate(nginx_upstream_responses_total{status=~"5.."}[2m]))
```

或者去 Grafana → "API Gateway Overview" 面板，按服务下钻。

---

**Q：upstream 报 502 和 504 有什么区别？**

- **502 Bad Gateway**：上游服务返回了无效响应，或连接被重置。通常是上游进程崩溃、OOM、或者在重启中。
- **504 Gateway Timeout**：上游没在超时时间内响应。通常是上游处理慢（数据库慢查询、外部依赖超时）或连接池耗尽。

502 → 先看上游服务是否在正常运行
504 → 先看上游服务的 P99 延迟和线程池/连接池状态

---

**Q：上游服务看起来正常，但网关还是报错，怎么回事？**

几个常见情况：
1. **连接池耗尽**：网关到上游的连接数超限，新请求排队超时。检查 `nginx_upstream_connections` 指标。
2. **健康检查和实际流量不一致**：健康检查路径正常但业务接口有问题。
3. **刚发布的版本有 bug**：对比发布时间和错误率上升时间。

```bash
# 查看网关连接池状态（在网关节点上）
curl http://localhost/nginx_status
```

---

**Q：是不是流量太高打垮上游了？**

```promql
# 看 QPS 趋势
sum(rate(nginx_http_requests_total[1m]))
```

对比历史同期，如果 QPS 无异常但错误率高，说明是服务质量问题，不是容量问题。
如果 QPS 确实暴增，走限流流程（联系平台组开启 rate limiting）。

---

**Q：要不要回滚？**

满足以下任一条件建议立即回滚：
- 错误率 > 5% 且持续超过 5 分钟
- 有明确的版本关联（发布后立即出现）
- 影响到 P0 核心链路

回滚命令（Kubernetes 部署）：
```bash
kubectl rollout undo deployment/<service-name> -n <namespace>
kubectl rollout status deployment/<service-name> -n <namespace>
```

---

**Q：错误率降下去了，还需要做什么？**

1. 确认是否写了 incident ticket（P1 以上必须）
2. 保留现场：收集报错期间的日志、metrics 截图
3. 如果是偶发且影响小，记录到 #oncall-log 频道即可
4. 影响较大的走正式复盘，参考 postmortem 模板

---

*相关：runbook_service_timeout.md / reference_service_topology.md*
