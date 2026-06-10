# 负载均衡健康检查失败处理

**告警**：`LoadBalancerUnhealthyBackends` / `NginxUpstreamDown`

---

## 排查 Checklist

按顺序逐项确认，找到根因后可跳过后续步骤。

### □ 1. 确认影响范围

```bash
# 看所有 upstream 的健康状态（nginx plus / tengine）
curl http://localhost/upstream_status 2>/dev/null | jq .

# 标准 nginx 看 error log
kubectl logs <nginx-pod> -n <ns> --tail=200 | grep "upstream"
```

只有个别 backend 不健康 → 问题在特定实例，不影响整体
所有 backend 都不健康 → 全面故障，立即升级

### □ 2. 上游服务 Pod 是否存活

```bash
kubectl get pods -n <upstream-namespace> -l app=<upstream-service>
# 有 CrashLoopBackOff / Error / Pending → 上游服务问题，先修上游
```

### □ 3. 健康检查接口本身是否正常

```bash
# 直接访问健康检查接口
kubectl exec -it <nginx-pod> -- curl -v http://<upstream-pod-ip>:<port>/health
```

健康检查接口返回非 200：
- 应用正在重启（短暂性）→ 等 30 秒再看
- 应用卡死但进程存活 → 需要重启应用
- 健康检查接口有 bug → 联系开发

健康检查接口返回 200 但负载均衡仍标记不健康：
- 可能是健康检查配置问题（超时太短、检查间隔太频繁）

### □ 4. 网络连通性

```bash
# 在 nginx pod 里测试到上游的连通性
kubectl exec -it <nginx-pod> -- curl -v --connect-timeout 5 http://<upstream-ip>:<port>/health

# 检查 NetworkPolicy 是否有限制
kubectl get networkpolicy -n <upstream-namespace>
```

### □ 5. 资源是否耗尽

```bash
# 上游 Pod 的资源使用
kubectl top pod -n <upstream-namespace> -l app=<upstream-service>

# 是否有大量 TCP 连接积压
kubectl exec -it <upstream-pod> -- ss -s
```

---

## 临时缓解措施

**将故障实例从负载均衡摘除（Nginx upstream 手动下线）**

如果是少数实例故障，可以临时将其从 upstream 配置中摘除，让健康实例承接流量：

```bash
# 修改 configmap 或 nginx.conf
# 注意：摘除实例会增加其他实例的负载，确认其他实例能承受
```

**扩容健康实例**

```bash
kubectl scale deployment <upstream-service> -n <upstream-namespace> --replicas=<N+2>
```

---

## 健康检查参数调优

如果频繁出现误判（实例实际健康但被标记不健康），考虑调整参数：

```nginx
upstream backend {
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;

    # 连续失败 3 次才标记不健康（默认 1 次）
    # 30 秒后重新检查（默认更短）
}
```

具体参数根据业务容忍度调整，改配置需要 reload nginx：
```bash
kubectl exec -it <nginx-pod> -- nginx -s reload
```

---

## 升级条件

| 场景 | 等级 |
|------|------|
| 单个 backend 不健康，其他正常 | P3，工作时间处理 |
| 50% 以上 backend 不健康 | P1，立即处理 |
| 全部 backend 不健康，服务不可用 | P0，叫所有人 |
| 网关节点本身有问题 | P0 |
