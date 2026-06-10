# Pod Pending 排查手册

适用场景：Pod 长时间处于 `Pending` 状态，未被调度到任何节点。

---

## 快速定位

```bash
# 看 Pod 事件，99% 的原因在这里
kubectl describe pod <pod-name> -n <namespace>
# 重点看最底部的 Events 段
```

常见 Events 和对应原因：

```
0/5 nodes are available: 3 Insufficient memory, 2 node(s) had taint...
```
→ 资源不足或节点污点，见下文对应章节。

```
0/5 nodes are available: 5 node(s) didn't match Pod's node affinity/selector
```
→ 亲和性/选择器配置有误，检查 Pod spec。

```
persistentvolumeclaim "xxx" not found
```
→ PVC 不存在或 StorageClass 有问题。

---

## 资源不足

```bash
# 看各节点可用资源
kubectl describe nodes | grep -A 5 "Allocated resources"

# 或者用 top（需要 metrics-server）
kubectl top nodes
```

节点资源够但还是调度不上去？检查是否有 `LimitRange` 或 `ResourceQuota` 卡住：
```bash
kubectl describe limitrange -n <namespace>
kubectl describe resourcequota -n <namespace>
```

**临时解法**：如果是测试环境，可以降低 Pod 的 `resources.requests`。生产环境需要走扩容流程（见 capacity_planning_guide.md）。

---

## 节点污点问题

```bash
# 查看节点污点
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints

# 如果 Pod 需要调度到有污点的节点，需要加 tolerations
```

Taint 格式：`key=value:Effect`，Effect 有三种：
- `NoSchedule`：不调度新 Pod
- `PreferNoSchedule`：尽量不调度
- `NoExecute`：驱逐已有 Pod

```yaml
# Pod spec 中加 tolerations 示例
tolerations:
  - key: "dedicated"
    operator: "Equal"
    value: "gpu"
    effect: "NoSchedule"
```

---

## PVC / 存储问题

```bash
kubectl get pvc -n <namespace>
# 看 STATUS，Pending 说明 PV 没绑上

kubectl describe pvc <pvc-name> -n <namespace>
```

PVC Pending 的常见原因：
1. StorageClass 不存在：`kubectl get storageclass`
2. 没有满足条件的 PV（静态供给场景）
3. 动态供给的 provisioner 挂了：`kubectl get pods -n kube-system | grep provisioner`

---

## 镜像拉取失败导致卡 Pending

严格来说是 `ImagePullBackOff` 而不是 `Pending`，但有时候 Events 里看到的是这个：
```bash
kubectl describe pod <pod> -n <ns> | grep -A 3 "Failed"
```

常见原因：私有仓库没配 `imagePullSecrets`，或镜像 tag 不存在。

```bash
# 确认 secret 是否存在
kubectl get secret regcred -n <namespace>

# 手动测试拉镜像（在节点上）
docker pull <image>:<tag>
```

---

## 调度器问题（少见）

如果以上都没问题，考虑调度器本身：
```bash
kubectl get pods -n kube-system | grep scheduler
kubectl logs -n kube-system kube-scheduler-<node> --tail=50
```

---

## 升级路径

| 等待时间 | 操作 |
|----------|------|
| < 10min | 继续排查 |
| 10-30min | 通知业务方，评估回滚 |
| > 30min | 升级到平台组 on-call |
