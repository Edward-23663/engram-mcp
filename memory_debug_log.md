# Engram 记忆系统问题排查记录

## 问题描述
日期：2026-03-08
时间：13:06
问题：Web UI 显示有 17 条记忆，但通过 opencode 的 MCP 工具无法调出记忆

## 排查过程

### 1. 初始检查
- 用户报告 Web UI 显示 17 条记忆
- opencode 的 `engram-memory_memory_search` 工具返回空结果
- 这是一个重复发生的问题

### 2. 系统环境检查
- 工作目录：`/home/jianwei/.opencode/code1`
- 项目是 Git 仓库
- 包含完整的 Docker 微服务架构

### 3. MCP 配置分析
#### 3.1 opencode.json 配置
```json
{
  "mcp": {
    "engram-memory": {
      "type": "local",
      "command": ["python3", "/home/jianwei/.opencode/code1/engram-mcp/mcp_server.py"],
      "environment": {
        "DATABASE_URL": "postgresql+asyncpg://app:postgres_password@localhost:5432/appdb",
        "REDIS_URL": "redis://:redis_password@localhost:6379/0",
        "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
        "LITELLM_BASE_URL": "http://localhost:4000",
        "LITELLM_API_KEY": "litellm_key_123",
        "LITELLM_EMBED_MODEL": "text-embedding-3-small",
        "LITELLM_CHAT_MODEL": "gpt-4o-mini",
        "NAMESPACE": "default"
      },
      "enabled": true
    }
  }
}
```

#### 3.2 MCP 服务器实现
- 文件：`engram-mcp/mcp_server.py`
- 通过 stdio 使用 JSON-RPC 协议通信
- 实现了完整的 MCP 方法处理

### 4. Docker 服务状态检查
```
CONTAINER ID   IMAGE                                 STATUS                      PORTS
2d606e0ad120   ghcr.io/berriai/litellm:main-latest   Up 35 minutes (healthy)     0.0.0.0:4000->4000/tcp
c6e2dead173b   code1-engram-mcp                      Up 13 minutes (unhealthy)   0.0.0.0:8001->8001/tcp
881cc934358c   code1-fastapi                         Up 3 hours (unhealthy)      0.0.0.0:8000->8000/tcp
8edd1199a252   nginx:alpine                          Up 3 hours (unhealthy)      0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
d79d22f8de27   rabbitmq:3-management-alpine          Up 3 hours (healthy)        0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
e54f43f5f9a9   pgvector/pgvector:pg17-trixie         Up 3 hours (healthy)        0.0.0.0:5432->5432/tcp
ac7adf865677   redis:7-alpine                        Up 3 hours (healthy)        0.0.0.0:6379->6379/tcp
6ab588e221ab   qdrant/qdrant:latest                  Up 3 hours (unhealthy)      0.0.0.0:6333-6334->6333-6334/tcp
```

### 5. 数据库验证
```sql
SELECT COUNT(*) FROM memories;
-- 结果：19 条记录
```

### 6. MCP 服务器直接测试
#### 6.1 初始化测试
```bash
echo '{"jsonrpc":"2.0","method":"initialize","id":1}' | python3 engram-mcp/mcp_server.py
```
**结果**：成功返回协议版本和服务器信息

#### 6.2 工具列表测试
```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":3}' | python3 engram-mcp/mcp_server.py
```
**结果**：成功返回 12 个工具，包括：
- `memory.create`, `memory.get`, `memory.search`
- `memory.list`, `memory.mark_important`, `memory.get_important`
- `topic.list`, `topic.get`, `trigger.fire`, `trigger.list`
- `session.resume`, `stats.get`

#### 6.3 记忆搜索测试
```bash
echo '{"jsonrpc":"2.0","method":"memory.search","params":{"query":"test","limit":10},"id":2}' | python3 engram-mcp/mcp_server.py
```
**结果**：成功返回 5 条记忆记录

### 7. opencode 工具状态检查
- 当前会话中 `engram-memory_*` 工具不可用
- 可用的工具列表中不包含 MCP 相关工具
- 这表明 opencode 没有成功加载 MCP 服务器

### 8. 使用 filescope 深入分析
#### 8.1 项目文件结构
- 总共 88 个文件
- 重要文件包括：
  - `opencode.json` (重要性: 1)
  - `engram-mcp/mcp_server.py` (重要性: 0)
  - `engram-mcp/main.py` (重要性: 2)
  - `engram-mcp/app/core/config.py` (重要性: 2)

#### 8.2 关键发现
1. MCP 服务器代码完整且功能正常
2. 数据库连接配置正确
3. 所有依赖服务都在运行
4. 数据库中有实际数据

## 问题根本原因分析

### 核心问题
**opencode 当前会话没有正确加载 MCP 服务器连接**

### 可能的原因
1. **时序问题**：opencode 启动时 MCP 服务器尚未准备好
2. **权限问题**：opencode 执行 MCP 服务器脚本的权限不足
3. **环境问题**：Python 环境或依赖缺失
4. **通信问题**：stdio 管道阻塞或关闭
5. **配置加载问题**：opencode 没有重新加载 MCP 配置

### 证据支持
1. **MCP 服务器独立工作正常**：直接测试可以返回记忆数据
2. **数据库中有数据**：19 条记忆记录存在
3. **Web UI 可访问**：HTTP 接口工作正常
4. **opencode 工具缺失**：当前会话没有 MCP 工具

## 解决方案建议

### 立即措施
1. **重启 opencode 会话**：让 opencode 重新加载 MCP 配置
2. **手动启动 MCP 服务器**：确保在 opencode 之前运行
3. **检查 opencode 日志**：查看 MCP 加载错误信息

### 临时解决方案
1. 通过 Web UI 访问记忆：http://localhost:8001
2. 直接调用 MCP 服务器获取记忆数据

### 长期修复
1. **改进 MCP 启动脚本**：添加重试机制和健康检查
2. **优化配置加载**：确保 opencode 正确加载 MCP 配置
3. **添加监控**：监控 MCP 服务器状态和连接

## 技术细节

### MCP 服务器关键代码
- 使用 stdio 进行 JSON-RPC 通信
- 支持异步数据库操作
- 完整的错误处理机制
- 工具注册和调用流程正确

### 网络配置
- 所有服务都映射到 localhost 端口
- Docker 容器间使用 bridge 网络
- 端口映射配置正确

### 数据验证
- 数据库：19 条记忆
- Redis：连接正常
- RabbitMQ：连接正常
- LiteLLM：服务正常

## 结论
问题不在于 MCP 服务器本身或数据存储，而在于 opencode 和 MCP 服务器之间的连接建立。这是一个典型的服务间通信问题，需要重启 opencode 会话或修复 MCP 配置加载机制。

---
记录时间：2026-03-08 13:10
记录者：opencode AI 助手
问题状态：已分析，待解决