# Engram MCP 自动自愈系统配置指南

## 概述

这个系统会在 opencode 启动时自动运行，确保 Engram MCP 服务正常工作。它包括：
1. **自动测试** - 检查 MCP 服务器功能
2. **自动运行** - 启动 MCP 服务器（如果需要）
3. **自动修复** - 检测并修复常见问题
4. **健康监控** - 持续监控 MCP 服务状态

## 系统组件

### 1. 核心自愈脚本
- `engram-mcp/mcp_auto_healer.py` - 主自愈逻辑
- 功能：测试、启动、修复、监控 MCP 服务
- 日志：`/tmp/engram_mcp_healer.log`

### 2. 启动管理脚本
- `start_mcp_healer.sh` - 启动/停止/状态管理
- 命令：`start|stop|restart|status|test`
- PID 文件：`/tmp/engram_mcp_healer.pid`

### 3. OpenCode 启动钩子
- `.opencode/hooks/startup.sh` - opencode 启动时自动运行
- 日志：`/tmp/opencode_startup_hook.log`

## 安装和配置

### 步骤 1：确保脚本可执行
```bash
chmod +x engram-mcp/mcp_auto_healer.py
chmod +x start_mcp_healer.sh
chmod +x .opencode/hooks/startup.sh
```

### 步骤 2：测试系统
```bash
# 测试 MCP 服务器
./start_mcp_healer.sh test

# 启动自愈系统
./start_mcp_healer.sh start

# 检查状态
./start_mcp_healer.sh status
```

### 步骤 3：验证 opencode 启动钩子
```bash
# 手动运行启动钩子测试
./.opencode/hooks/startup.sh
```

## 使用方法

### 手动管理
```bash
# 启动自愈系统
./start_mcp_healer.sh start

# 停止自愈系统
./start_mcp_healer.sh stop

# 重启自愈系统
./start_mcp_healer.sh restart

# 检查状态
./start_mcp_healer.sh status

# 测试 MCP 服务器
./start_mcp_healer.sh test
```

### 自动启动（推荐）
当 opencode 启动时，会自动执行 `.opencode/hooks/startup.sh`，该脚本会：
1. 检查并启动自愈系统
2. 测试 MCP 服务器功能
3. 记录启动日志

## 监控和故障排除

### 查看日志
```bash
# 自愈系统日志
tail -f /tmp/engram_mcp_healer.log

# 启动钩子日志
tail -f /tmp/opencode_startup_hook.log

# 启动脚本日志
tail -f /tmp/engram_mcp_startup.log
```

### 常见问题

#### 问题 1：MCP 服务器无法启动
**症状**：`./start_mcp_healer.sh test` 失败
**解决方案**：
```bash
# 检查 Docker 服务
docker ps

# 手动测试 MCP
cd /home/jianwei/.opencode/code1
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python3 engram-mcp/mcp_direct.py
```

#### 问题 2：自愈系统无法启动
**症状**：`./start_mcp_healer.sh status` 显示 STOPPED
**解决方案**：
```bash
# 检查依赖
python3 --version
docker --version

# 检查权限
ls -la engram-mcp/mcp_auto_healer.py
ls -la start_mcp_healer.sh

# 查看详细错误
cd /home/jianwei/.opencode/code1
python3 engram-mcp/mcp_auto_healer.py
```

#### 问题 3：opencode 启动钩子不工作
**症状**：opencode 启动时没有自动启动自愈系统
**解决方案**：
1. 确保钩子脚本可执行
2. 检查 opencode 配置
3. 手动运行钩子测试

## 系统工作原理

### 1. 启动流程
```
opencode 启动
    ↓
执行 .opencode/hooks/startup.sh
    ↓
运行 start_mcp_healer.sh start
    ↓
启动 mcp_auto_healer.py
    ↓
测试 MCP 服务器 → 失败则修复
    ↓
启动健康监控
```

### 2. 健康监控
- 每 60 秒检查一次 MCP 服务
- 检测到故障时自动修复
- 修复失败时重启 MCP 服务器
- 监控依赖服务（数据库、Redis）

### 3. 修复能力
- 检查并重启 Docker 服务
- 验证数据库连接
- 测试 MCP 服务器功能
- 重启故障的 MCP 进程

## 配置选项

### 环境变量
可以在 `mcp_auto_healer.py` 中修改：
```python
CONFIG = {
    'health_check_port': 18084,      # 健康检查端口
    'max_retries': 3,                # 最大重试次数
    'retry_delay': 2,                # 重试延迟（秒）
    'test_timeout': 10,              # 测试超时（秒）
    'check_interval': 60,            # 健康检查间隔（秒）
}
```

### 日志配置
- 日志级别：INFO（可改为 DEBUG 查看更多细节）
- 日志位置：`/tmp/engram_mcp_healer.log`
- 同时输出到控制台和文件

## 安全注意事项

1. **PID 文件**：存储在 `/tmp` 目录，系统重启时清除
2. **日志文件**：包含服务状态信息，不包含敏感数据
3. **权限**：脚本需要执行权限，但不需要特殊权限
4. **网络**：仅访问本地服务（localhost）

## 性能影响

- **CPU**：健康检查消耗极少 CPU
- **内存**：Python 进程约 10-20MB
- **网络**：仅本地连接，无外部网络请求
- **启动时间**：增加约 2-3 秒启动延迟

## 故障恢复

系统设计为自我恢复：
1. **进程崩溃**：通过 PID 文件检测并重启
2. **服务故障**：健康检查检测并修复
3. **依赖故障**：检查并尝试重启依赖服务
4. **网络问题**：重试机制处理临时故障

## 支持与反馈

如果遇到问题：
1. 检查日志文件获取详细信息
2. 运行 `./start_mcp_healer.sh test` 测试基本功能
3. 查看本文档的故障排除部分
4. 检查系统依赖是否满足

## 更新历史

- **2026-03-08**：初始版本创建
- 功能：自动测试、运行、修复 MCP 服务
- 集成：opencode 启动钩子
- 监控：健康检查和自动修复

---

**注意**：此系统专为解决 Engram MCP 在 opencode 启动时的连接问题而设计。它确保 MCP 服务始终可用，即使遇到临时故障也能自动恢复。