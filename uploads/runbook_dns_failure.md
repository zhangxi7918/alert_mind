# DNS 解析失败处理

**告警**：`DNSResolutionFailureRate` / 应用日志大量 `no such host` / `dial tcp: lookup xxx: i/o timeout`

---

## 确认是 DNS 问题

```bash
# 在出问题的 Pod 里测试
kubectl exec -it <pod> -n <ns> -- nslookup kubernetes.default
kubectl exec -it <pod> -n <ns> -- nslookup <service-name>.<namespace>.svc.cluster.local

# 如果 nslookup 不可用
kubectl exec -it <pod> -n <ns> -- cat /etc/resolv.conf
kubectl exec -it <pod> -n <ns> -- curl -v telnet://kube-dns.kube-system.svc.cluster.local:53
```

---

## 检查 CoreDNS

```bash
# CoreDNS Pod 是否正常
kubectl get pods -n kube-system -l k8s-app=kube-dns

# CoreDNS 日志
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100

# CoreDNS 指标（如果暴露了）
kubectl port-forward -n kube-system svc/kube-dns 9153:9153
curl http://localhost:9153/metrics | grep coredns_dns_request_duration
```

CoreDNS 重启次数多？看原因：
```bash
kubectl describe pod -n kube-system -l k8s-app=kube-dns | grep -A 5 "Last State"
```

---

## 常见原因和处理

**CoreDNS OOM**：
```bash
kubectl top pod -n kube-system -l k8s-app=kube-dns
# 内存接近 limit → 临时调高 limit 或扩容 CoreDNS 副本
kubectl scale deployment coredns -n kube-system --replicas=3
```

**ndots 配置导致查询风暴**：
Pod 内 `/etc/resolv.conf` 的 `ndots:5` 会让每个域名查询最多尝试 6 次（加各种后缀），高并发下会打爆 CoreDNS。
```bash
# 临时：用 FQDN（完整域名加最后的点）
nslookup kubernetes.default.svc.cluster.local.
# 根本解法：修改 Pod dnsConfig 将 ndots 调低
```

**节点 iptables 规则异常**：
```bash
# 在节点上检查 kube-dns service 的 iptables 规则
iptables -t nat -L KUBE-SERVICES | grep dns
# 规则消失或错误 → 重启 kube-proxy
```

**CoreDNS ConfigMap 配置错误**：
```bash
kubectl get configmap coredns -n kube-system -o yaml
# 修改后需要重启 CoreDNS
kubectl rollout restart deployment/coredns -n kube-system
```

---

## 外部 DNS 问题

集群内 DNS 正常，但解析外部域名失败：
```bash
# 测试外部解析
kubectl exec -it <pod> -n <ns> -- nslookup google.com

# CoreDNS forward 配置
kubectl get configmap coredns -n kube-system -o yaml | grep forward
# 检查 forward 目标（通常是节点 DNS 或 8.8.8.8）是否可达
```

---

## 升级条件

- CoreDNS 全部 Pod 不可用 → 立即 P0，叫人
- 解析失败率 > 10% 且持续 > 5 分钟 → P1
- 单个命名空间受影响 → P2，工作时间处理
