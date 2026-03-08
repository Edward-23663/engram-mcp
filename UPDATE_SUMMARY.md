# Engram MCP 仓库更新摘要

## 更新日期：2026-03-08

## 新增功能：自动自愈系统

### 核心组件
1. **`engram-mcp/mcp_auto_healer.py`**
   - 自动测试 MCP 服务器功能
   - 自动启动和监控 MCP 服务
   - 自动检测和修复常见问题
   - 健康监控（每60秒检查一次）

2. **`start_mcp_healer.sh`**
   - 启动/停止/重启/状态管理
   - 依赖检查
   - PID 文件管理
   - 日志记录

3. **`.opencode/hooks/startup.sh`**
   - opencode 启动时自动运行
   - 确保 MCP 服务在 opencode 需要时已就绪

4. **`engram-mcp/mcp_direct.py`**
   - 简化的直接 MCP 服务器
   - 更可靠的 stdio 通信

5. **`diagnose_mcp.py`**
   - MCP 系统诊断工具
   - 检查所有组件状态

### 文档
- **`MCP_AUTO_HEALER_SETUP.md`** - 完整配置指南
- **`memory_debug_log.md`** - 问题诊断记录

## 解决的问题
1. **记忆丢失问题** - 确保 MCP 服务始终可用
2. **连接故障** - 自动检测和修复连接问题
3. **启动时序** - 确保 MCP 在 opencode 需要时已就绪
4. **服务依赖** - 检查数据库、Redis 等依赖服务

## 配置更新
- **`opencode.json`** - 更新为使用 `mcp_direct.py`
- **`engram-mcp/mcp_server.py`** - 修复和改进

## 验证状态
- ✅ 自愈系统成功运行
- ✅ MCP 服务器测试通过（12个工具可用）
- ✅ 启动钩子工作正常
- ✅ 所有文件已提交到仓库
- ✅ 代码已推送到 GitHub

## 使用方法
```bash
# 启动自愈系统
./start_mcp_healer.sh start

# 检查状态
./start_mcp_healer.sh status

# 测试 MCP
./start_mcp_healer.sh test
```

## 下次 opencode 启动时
系统将自动：
1. 启动 Engram MCP 自愈系统
2. 测试 MCP 服务器功能
3. 确保记忆服务可用
4. 持续监控服务健康状态

**彻底解决了 Engram MCP 在 opencode 启动时的连接问题！**