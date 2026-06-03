# 磁盘空间不足处理手册

## 告警说明

告警名称：DiskSpaceLow / DiskSpaceCritical
触发条件：磁盘使用率超过 80%（Warning）或 90%（Critical）
严重等级：Warning / Critical
负责团队：基础设施运维组

## 排查步骤

### 第一步：确认磁盘使用情况

```bash
# 查看各挂载点磁盘使用率
df -hT

# Prometheus 查询磁盘使用率
(1 - node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"}) * 100
```

重点关注 `/`（根分区）、`/var`（日志和容器数据）、`/data`（业务数据）三个挂载点。

### 第二步：找出占用磁盘最多的目录

```bash
# 从根目录开始，逐层定位大文件/目录（避免扫描 /proc /sys）
du -h --max-depth=2 / --exclude=/proc --exclude=/sys 2>/dev/null | sort -rh | head -20

# 查找超过 500MB 的文件
find / -xdev -type f -size +500M 2>/dev/null | xargs ls -lh

# Docker 场景：查看 Docker 占用空间
docker system df
```

### 第三步：清理常见磁盘占用

**清理日志文件**：

```bash
# 查看 journald 日志大小
journalctl --disk-usage

# 清理 30 天前的日志
journalctl --vacuum-time=30d

# 清理超过 500MB 的日志
journalctl --vacuum-size=500M

# 检查应用日志目录
ls -lh /var/log/
find /var/log -name "*.log" -mtime +7 -exec ls -lh {} \;
```

**清理 Docker 无用资源**：

```bash
# 查看可清理的资源
docker system df

# 删除停止的容器、无标签镜像、无用网络（谨慎，不可恢复）
docker system prune -f

# 删除无用数据卷（更危险，需确认无业务数据）
docker volume prune -f
```

**清理包管理器缓存**：

```bash
# Debian/Ubuntu
apt-get clean && apt-get autoremove -y

# CentOS/RHEL
yum clean all
```

### 第四步：临时扩容（若清理不足）

- 若是云主机，联系云平台扩展数据盘容量
- 扩展后执行分区扩容：`growpart /dev/vda 1 && resize2fs /dev/vda1`
- 若无法立即扩容，将部分日志或数据迁移至备用存储路径

### 第五步：永久修复

- 配置日志轮转（logrotate）限制单文件大小和保留天数
- 为 Docker 数据目录设置磁盘配额或单独挂载大容量磁盘
- 在 Prometheus 中调低告警阈值（如提前在 75% 时预警），留出处置时间窗口

## 升级路径

| 磁盘使用率 | 操作 |
|------------|------|
| 80%–85% | 清理日志，通知运维 |
| 85%–90% | 执行全量清理，通知业务负责人 |
| > 90% | 立即启动应急响应，暂停写入操作，联系扩容 |

## 相关文档

- Prometheus 告警规则：`prometheus/alert_rules.yml`
- 日志管理规范：`docs/logging_policy.md`
- 云主机扩容操作指引：`runbook_scaling.md`
