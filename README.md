# Engram MCP - 情境感知自动记忆系统

[English](./README_EN.md) | 中文

## 概述

Engram MCP 是一个基于"情境感知自动记忆系统"的 MCP（Model Context Protocol）服务，模拟人脑记忆机制，实现全自动化记忆管理。系统复刻并扩展了 engram-rs 的记忆生命周期管理逻辑。

## 核心特性

### 🎯 全自动化
- **自动感知**：监听外部事件，自动捕获记忆
- **自动存储**：接收到记忆后自动持久化
- **自动分类**：LLM 判断记忆类型（episodic/semantic/procedural）
- **自动分层**：三层记忆生命周期（Buffer→Working→Core）
- **自动压缩**：语义去重、主题蒸馏
- **自动清理**：基于艾宾浩斯遗忘曲线
- **自动触发**：trigger 标签触发检索

### 🧠 智能记忆管理
- **三层记忆模型**：
  - Buffer（缓冲层）：短期记忆，可被删除
  - Working（工作层）：中期记忆，重要信息
  - Core（核心层）：永久记忆，永不删除

- **重要记忆保护**：
  - 手动标记重要记忆
  - 自动保护（高频访问、高质量内容）
  - LLM 智能评估

- **记忆类型**：
  - episodic：情景记忆
  - semantic：语义记忆
  - procedural：程序记忆

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                      Nginx (80)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Web UI    │  │  API Proxy  │  │  其他服务   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   Engram MCP (8001)                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐ │
│  │  FastAPI │ │ Workers │ │  LLM    │ │ MCP Adapter │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────┘
         ↓              ↓            ↓
┌──────────┐   ┌──────────┐   ┌──────────┐
│PostgreSQL│   │  RabbitMQ │   │   Redis  │
│+pgvector │   │           │   │          │
└──────────┘   └──────────┘   └──────────┘
                           ↓
                    ┌──────────┐
                    │  LiteLLM │
                    └──────────┘
```

## 快速开始

### 前置要求

- Docker ≥ 20.10
- Docker Compose ≥ 2.0

### 1. 启动所有服务

```bash
# 克隆项目后直接启动
docker-compose up -d
```

### 2. 检查服务状态

```bash
docker-compose ps
```

### 3. 访问服务

| 服务 | 地址 | 默认凭据 |
|------|------|----------|
| Web UI | http://localhost/ | - |
| Engram API | http://localhost:8001 | - |
| API 文档 | http://localhost:8001/docs | - |
| LiteLLM | http://localhost:4000 | 密钥: litellm_key_123 |
| RabbitMQ | http://localhost:15672 | guest/guest |
| PostgreSQL | localhost:5432 | app/postgres_password |

### 4. 配置 LiteLLM（可选）

在 `.env` 文件中设置 LLM API 密钥：

```bash
OPENAI_API_KEY=sk-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## 使用示例

### 创建记忆

```bash
curl -X POST http://localhost:8001/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "content": "用户偏好深色主题模式",
    "tags": ["偏好", "UI"],
    "context": {"source": "user_feedback"}
  }'
```

### 搜索记忆

```bash
curl -X POST http://localhost:8001/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "用户主题偏好",
    "layers": ["buffer", "working", "core"],
    "memory_types": ["semantic"],
    "limit": 10
  }'
```

### 标记重要记忆

```bash
curl -X POST "http://localhost:8001/api/v1/memories/{id}/mark-important?reason=core_identity"
```

### 创建触发器

```bash
curl -X POST http://localhost:8001/api/v1/triggers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "部署触发器",
    "trigger_tag": "trigger:deploy",
    "query_text": "部署相关记忆",
    "layers": ["core", "working"],
    "limit": 5
  }'
```

### 会话恢复

```bash
curl http://localhost:8001/api/v1/resume
```

## API 接口文档

完整 API 文档请访问：http://localhost:8001/docs

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/memories` | 创建记忆 |
| GET | `/api/v1/memories/{id}` | 获取记忆 |
| POST | `/api/v1/memories/search` | 搜索记忆 |
| POST | `/api/v1/memories/{id}/mark-important` | 标记重要 |
| POST | `/api/v1/memories/{id}/promote` | 晋升记忆 |
| GET/POST | `/api/v1/topics` | 主题管理 |
| GET/POST | `/api/v1/triggers` | 触发器管理 |
| GET | `/api/v1/resume` | 会话恢复 |
| GET | `/api/v1/stats` | 统计信息 |

## MCP 集成

### OpenCode 配置

```json
{
  "mcpServers": {
    "context-memory": {
      "command": "npx",
      "args": ["-y", "context-memory-mcp"],
      "env": {
        "ENGRAM_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

### Cursor/Windsurf 配置

```json
{
  "mcpServers": {
    "context-memory": {
      "command": "npx",
      "args": ["-y", "context-memory-mcp"],
      "env": {
        "ENGRAM_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

## 工作机制

### 1. 自动记忆流程
```
用户输入 → API接收 → RabbitMQ队列 → 存储服务 → PostgreSQL+向量
                                        ↓
                              LLM分类 → 类型/质量评估
```

### 2. 自动晋升流程
```
定时任务 → 扫描候选记忆 → LLM门控评估
                                  ↓
                    Buffer→Working→Core
                                  ↓
                      重要标记（is_important=true）
```

### 3. 自动清理流程
```
定时任务 → 扫描Buffer层 → 计算衰减分数
                              ↓
                    低于阈值(0.01) → 归档 → 删除
                              ↓
                    重要记忆 → 跳过（保护）
```

### 4. 触发检索流程
```
外部事件 → trigger:标签 → 解析规则
                              ↓
            混合检索 → Sigmoid评分 → 返回结果
                              ↓
                        更新访问计数
```

## 重要记忆保护规则

### 自动保护条件
1. **高访问频率**: 访问次数 ≥ 10 次
2. **高质量语义记忆**: 质量评分 ≥ 0.8 的语义记忆
3. **程序技能**: 质量评分 ≥ 0.7 的程序记忆
4. **关键词触发**: 包含 "important", "critical", "key" 且质量 ≥ 0.6
5. **LLM 评估**: 晋升时 LLM 判断应该标记为重要

### 保护来源
- `user`: 用户手动标记
- `llm`: LLM 评估后自动标记
- `high_quality_semantic`: 高质量语义记忆
- `procedural_skill`: 程序技能
- `frequent_access`: 高频访问
- `content_keywords`: 关键词触发

## 配置说明

### 环境变量

在 `.env` 文件中配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql://app:postgres_password@postgres:5432/appdb` |
| `REDIS_URL` | Redis 连接地址 | `redis://redis:6379/0` |
| `RABBITMQ_URL` | RabbitMQ 连接地址 | `amqp://guest:guest@rabbitmq:5672/` |
| `LITELLM_BASE_URL` | LiteLLM 服务地址 | `http://litellm:4000` |
| `LITELLM_API_KEY` | API 密钥 | `litellm_key_123` |
| `LITELLM_EMBED_MODEL` | 嵌入模型 | `text-embedding-3-small` |
| `LITELLM_CHAT_MODEL` | 对话模型 | `gpt-4o-mini` |
| `NAMESPACE` | 命名空间 | `default` |

## 目录结构

```
.
├── docker-compose.yml       # Docker 编排配置
├── .env                    # 环境变量配置
├── README.md               # 本文件
├── engram-mcp/            # 核心应用
│   ├── main.py            # 入口文件
│   ├── requirements.txt   # Python 依赖
│   ├── Dockerfile        # Docker 镜像构建
│   └── app/
│       ├── api/          # API 路由
│       ├── core/        # 核心模块
│       ├── models/      # 数据模型
│       ├── schemas/     # Pydantic 模型
│       ├── services/    # 业务服务
│       ├── workers/     # 后台任务
│       └── mcp/        # MCP 适配器
├── nginx/                # 反向代理配置
│   ├── nginx.conf
│   ├── conf.d/
│   └── html/            # Web UI
└── scripts/              # 脚本
    └── deploy.sh
```

## 常用命令

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f engram-mcp

# 重启 engram-mcp
docker-compose restart engram-mcp

# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v

# 进入 engram-mcp 容器
docker exec -it engram-mcp sh

# 查看 PostgreSQL
docker exec -it postgres psql -U app -d appdb

# 健康检查
curl http://localhost:8001/health
```

## 性能指标

| 指标 | 目标 |
|------|------|
| Docker 镜像大小 | ≤ 50MB |
| 运行内存占用 | ≤ 200MB |
| 检索延迟 | ≤ 500ms |
| 并发支持 | 100+ |

## 相关文档

- [开发日志](./docs/DEVELOPMENT_LOG.md)

## 许可证

MIT License
