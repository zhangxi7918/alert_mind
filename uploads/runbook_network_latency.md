# 网络延迟与丢包告警处理手册

## 告警说明

告警名称：HighNetworkLatency / PacketLoss
触发条件：服务间 P99 延迟超过 200ms 持续 2 分钟，或丢包率超过 1%
严重等级：Warning（延迟）/ Critical（丢包 > 5%）
负责团队：网络运维组 / 基础设施运维组

## 排查步骤

### 第一步：确认告警范围

判断是单点问题还是大范围网络故障：

```bash
# 检查当前主机到网关的延迟
ping -c 20 <gateway_ip>

# 检查到目标服务的延迟
ping -c 20 <target_service_ip>

# 查看路由路径
traceroute <target_service_ip>
mtr --report --report-cycles 20 <target_service_ip>
```

如果只有单条链路延迟高，优先排查该链路两端的主机和交换机。
如果多条链路同时告警，优先排查核心交换机和上游出口。

### 第二步：检查网卡与内核网络状态

```bash
# 查看网卡错误统计
ip -s link show eth0
ethtool -S eth0 | grep -i error

# 查看内核 TCP 重传和丢包统计
ss -s
netstat -s | grep -E "retransmit|failed|error"

# 查看网络缓冲区是否溢出
cat /proc/net/snmp | grep -E "InErrors|OutErrors|RetransSegs"
```

### 第三步：排查 DNS 问题

DNS 解析慢会被误判为服务延迟：

```bash
# 测量 DNS 解析时间
time nslookup <service_hostname>
dig <service_hostname> | grep "Query time"

# 检查 /etc/resolv.conf 配置
cat /etc/resolv.conf
```

如果 DNS 解析超过 50ms，检查 DNS 服务器负载或切换为备用 DNS。

### 第四步：容器网络排查

在 Docker/Kubernetes 环境下，网络问题常见于 overlay 网络：

```bash
# 检查 Docker bridge 网络
docker network inspect bridge

# 查看 iptables 规则是否异常
iptables -L -n -v | grep DROP

# 检查连接跟踪表是否接近上限（满了会丢包）
cat /proc/sys/net/netfilter/nf_conntrack_count
cat /proc/sys/net/netfilter/nf_conntrack_max
```

连接跟踪表满是高并发场景常见丢包原因，临时修复：

```bash
sysctl -w net.netfilter.nf_conntrack_max=262144
```

### 第五步：带宽使用检查

```bash
# 实时查看各进程网络带宽
nethogs eth0

# 查看接口流量统计
iftop -i eth0

# 检查是否有异常大流量进程
ss -tnp | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10
```

## 临时缓解措施

| 场景 | 操作 |
|------|------|
| 单服务延迟高 | 重启该服务，观察是否恢复 |
| 连接跟踪表满 | 临时扩大 nf_conntrack_max |
| 带宽打满 | 限制异常进程带宽或迁移服务 |
| DNS 解析慢 | 切换 DNS 服务器，或在 /etc/hosts 添加静态解析 |

## 升级路径

| 严重程度 | 持续时长 | 操作 |
|----------|----------|------|
| Warning  | < 10 分钟 | 观察，记录 |
| Warning  | > 10 分钟 | 通知网络组，开始排查 |
| Critical | 即时 | 启动应急响应，评估服务降级 |

## 相关文档

- 服务依赖拓扑：`reference_service_topology.md`
- 告警规则配置：`reference_alert_rules.md`
- 容器重启排查：`runbook_container_restart.md`
