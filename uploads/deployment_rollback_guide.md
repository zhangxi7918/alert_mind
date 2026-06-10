# 部署与回滚操作指南

_适用于 Kubernetes 部署场景。非 K8s 服务（裸机/VM）见附录。_

---

## 发布前 Go/No-Go 检查

在执行发布之前确认以下全部通过，否则不发：

- [ ] CI 全绿（单测 + 集成测试）
- [ ] 已经过 staging 环境验证
- [ ] 本次变更有对应的 ticket/PR，且有人 review
- [ ] 数据库变更（如有）已在变更窗口内执行完毕
- [ ] 不在变更冻结期（见 change_freeze_policy.md）
- [ ] 已通知值班工程师（在 #change-announcements 发消息）
- [ ] 确认有回滚方案且回滚步骤已验证可行

---

## 标准发布流程

```bash
# 1. 更新镜像版本
kubectl set image deployment/<name> <container>=<image>:<new-tag> -n <namespace>

# 2. 观察发布进度
kubectl rollout status deployment/<name> -n <namespace>
# 等待输出："successfully rolled out"

# 3. 发布后验证
# - 看 Pod 状态：kubectl get pods -n <namespace> | grep <name>
# - 看错误率：Grafana 或 kubectl logs
# - 看关键业务指标（根据服务不同，具体指标见各服务的 runbook）
```

**观察期**：发布完成后观察至少 5 分钟再离开。高风险变更观察 15 分钟。

---

## 回滚决策树

```
发布后出现异常？
├── 异常出现在发布后 5 分钟内？
│   └── 是 → 大概率是新版本引入，立即回滚（见下文）
├── 错误率 > 1% 或 P99 延迟上升 > 50%？
│   └── 是 → 立即回滚，事后再查原因
├── 异常是偶发且已自愈？
│   └── 是 → 继续观察，记录现象，暂不回滚
└── 不确定是否和发布相关？
    └── 先回滚，比起排查原因，回滚成本更低
```

**原则：宁可误回滚，不要赌它会自己好。**

---

## 回滚操作

### Kubernetes Deployment 回滚

```bash
# 查看发布历史
kubectl rollout history deployment/<name> -n <namespace>

# 回滚到上一个版本
kubectl rollout undo deployment/<name> -n <namespace>

# 回滚到指定版本
kubectl rollout undo deployment/<name> -n <namespace> --to-revision=<N>

# 确认回滚状态
kubectl rollout status deployment/<name> -n <namespace>
kubectl get pods -n <namespace> | grep <name>
```

### 数据库变更的回滚

数据库变更**不能用 `rollout undo`**。需要单独执行回滚 SQL。

回滚 SQL 必须在发布前准备好，并存放在 PR 的 description 里。如果没有准备回滚 SQL，这次变更不能发。

```bash
# 连接数据库执行回滚 SQL
kubectl exec -it <db-pod> -n <namespace> -- mysql -u root -p <dbname> < rollback.sql
```

### 配置变更的回滚

```bash
# ConfigMap 变更回滚
kubectl get configmap <name> -n <namespace> -o yaml > backup.yaml
# ... 执行变更 ...
# 回滚：
kubectl apply -f backup.yaml
kubectl rollout restart deployment/<name> -n <namespace>
```

---

## 金丝雀发布（灰度）

高风险变更建议走金丝雀：

```bash
# 保留旧 deployment，新建一个 canary deployment
kubectl apply -f deployment-canary.yaml

# 通过 Service 的 label selector 控制流量比例（需要配合流量管理工具）
# 或者直接控制 canary replicas 比例（粗粒度）

# 观察 canary 指标无异常后，全量切换
kubectl set image deployment/<name> <container>=<image>:<new-tag> -n <namespace>
kubectl delete deployment <name>-canary -n <namespace>
```

---

## 附录：裸机/VM 服务回滚

```bash
# 使用 systemd 管理的服务
sudo systemctl stop <service>
sudo cp /opt/app/bin/app.bak /opt/app/bin/app  # 替换二进制
sudo systemctl start <service>
sudo systemctl status <service>
```

回滚前确认备份存在：
```bash
ls -la /opt/app/bin/app.bak
# 备份时间戳要在发布之前
```

---

*相关：change_freeze_policy.md / oncall_handbook.md*
