# 容器频繁重启排查手册

## 告警说明

告警名称：ContainerRestartLoop
触发条件：容器 30 分钟内重启次数超过 3 次
严重等级：Warning（3-5 次）/ Critical（> 5 次）
负责团队：基础设施运维组 / 业务研发组

## 排查步骤

### 第一步：确认重启状态

```bash
# 查看所有容器状态和重启次数
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.RestartCount}}"

# 查看具体容器的详细信息
docker inspect <container_name> | jq '.[0].State'

# 查看容器退出码（退出码决定重启原因）
docker inspect <container_name> | jq '.[0].State.ExitCode'
```

**退出码速查：**

| 退出码 | 含义 |
|--------|------|
| 0 | 正常退出（主进程主动结束） |
| 1 | 应用内部错误 |
| 137 | OOM Kill（内存不足被系统杀掉） |
| 139 | Segmentation Fault（段错误） |
| 143 | 收到 SIGTERM 信号（被 Docker 停止） |
| 255 | 启动脚本返回错误 |

### 第二步：查看容器日志

```bash
# 查看当前容器日志（最近 100 行）
docker logs --tail 100 <container_name>

# 查看上一次退出前的日志（--previous 选项）
docker logs --previous --tail 100 <container_name>

# 实时跟踪日志
docker logs -f --since 10m <container_name>
```

**重点关注**：启动阶段报错、端口占用、配置文件缺失、数据库连接失败。

### 第三步：排查 OOM Kill（最常见原因）

退出码 137 或日志中出现 `Killed` 字样，表明是内存不足：

```bash
# 查看系统 OOM 日志
dmesg | grep -i "out of memory" | tail -20
journalctl -k | grep -i "oom" | tail -20

# 查看容器内存限制和当前使用
docker stats <container_name> --no-stream

# 查看容器是否设置了内存限制
docker inspect <container_name> | jq '.[0].HostConfig.Memory'
```

如果容器没有设置内存限制且宿主机内存不足，临时处理：

```bash
# 给容器设置内存限制，避免影响其他服务
docker update --memory="2g" --memory-swap="2g" <container_name>
```

### 第四步：排查启动依赖问题

容器反复重启的常见原因是启动时依赖的服务还没就绪：

```bash
# 检查依赖服务是否健康
docker ps | grep -E "mysql|redis|kafka|milvus"

# 检查容器启动命令
docker inspect <container_name> | jq '.[0].Config.Cmd'

# 查看容器间网络连通性
docker exec <container_name> ping <dependency_service>
docker exec <container_name> nc -zv <dependency_host> <port>
```

如果是启动顺序问题，在 `docker-compose.yml` 中添加 `depends_on` 和健康检查条件。

### 第五步：检查存储挂载问题

```bash
# 查看容器挂载的 volume
docker inspect <container_name> | jq '.[0].Mounts'

# 检查宿主机挂载目录的权限
ls -la <host_mount_path>

# 检查磁盘空间（磁盘满也会导致容器启动失败）
df -h
```

## 临时缓解措施

```bash
# 暂停自动重启（先稳住，再排查）
docker update --restart=no <container_name>

# 手动进入容器排查环境
docker run -it --entrypoint=/bin/sh <image_name>

# 查看容器内进程
docker exec <container_name> ps aux
```

## 升级路径

| 场景 | 操作 |
|------|------|
| 单容器重启，业务无感知 | 自主排查，30 分钟内解决 |
| 核心服务容器重启 | 立即通知业务负责人，并发排查 |
| 多容器同时重启 | 评估宿主机资源（CPU/内存/磁盘），升级为 P1 事故 |

## 相关文档

- 内存不足处理手册：`runbook_high_memory.md`
- 磁盘空间不足处理手册：`runbook_disk_space.md`
- 服务依赖拓扑：`reference_service_topology.md`
