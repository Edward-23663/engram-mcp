# Engram MCP 开发记录

## 开发日期
2026-03-08

## 本次完成的工作

### 1. Docker 部署配置优化
- 优化了 `Dockerfile`，使用多阶段构建减少镜像体积
- 配置了健康检查 `HEALTHCHECK`

### 2. Nginx 反向代理配置
- 添加了 `engram-mcp` upstream
- 配置 Web UI 静态文件服务为默认服务
- 配置 API 路由代理到 engram-mcp

### 3. Web UI 开发
- 创建了 `nginx/html/index.html`
- 功能包括：
  - 仪表盘：记忆统计、类型分布
  - 记忆列表：搜索、过滤（按层级）
  - 主题树：层级展示
  - 触发器：规则管理

### 4. 后台任务调度
- 创建了 `app/workers/scheduler.py`
- 定时任务：
  - 衰减任务（每小时）
  - 清理任务（每6小时）
  - 合并任务（每12小时）
  - 晋升任务（每2小时）
- 在 `consumers.py` 中添加了晋升处理逻辑

### 5. 本地部署脚本
- 创建了 `scripts/deploy.sh`
- 支持 Docker 和本地裸跑两种模式

### 6. Bug 修复
- 修复 `VECTOR` 导入错误：使用自定义 `Vector` 类型
- 修复 SQL 查询错误：使用 `text()` 包装原生 SQL
- 修复 `MemoryUpdate` 未导入问题

### 7. 触发规则完善
- 扩展 `TriggerRule` 模型：
  - 添加 `description` 描述字段
  - 添加 `min_importance` 最低重要性过滤
  - 添加 `min_quality` 最低质量过滤
  - 添加 `is_important_only` 仅重要记忆选项
  - 添加 `priority` 优先级字段
  - 添加 `conditions` 自定义条件字段

### 8. 重要记忆永久保存机制
- 添加 `Memory` 模型新字段：
  - `is_important`: 是否标记为重要
  - `importance_reason`: 重要原因
  - `importance_score`: 重要性评分
  - `is_auto_protected`: 是否自动保护
  - `protection_source`: 保护来源（llm/user/system/frequent_access）
- LLM 新增功能：
  - `evaluate_importance()`: 评估记忆重要性
  - `should_mark_important()`: 判断是否应标记为重要
  - `detect_auto_protection()`: 自动检测保护模式
- 记忆服务新增：
  - `mark_important()`: 标记记忆为重要
  - `unmark_important()`: 取消重要标记
  - `check_and_auto_protect()`: 自动保护检查
  - `get_important_memories()`: 获取重要记忆列表
- 修改晋升逻辑：
  - 晋升到 Core 层时自动评估是否重要
  - 重要记忆自动标记为 `is_important`
- 修改清理逻辑：
  - 重要记忆和自动保护记忆不会被删除
- 新增 API 路由：
  - `POST /memories/{id}/mark-important`: 标记重要
  - `POST /memories/{id}/unmark-important`: 取消重要
  - `GET /memories/important`: 获取重要记忆列表
  - `POST /memories/{id}/promote`: 晋升记忆

## 部署状态

### 运行的服务
| 服务 | 端口 | 状态 |
|------|------|------|
| engram-mcp | 8001 | ✅ running |
| nginx | 80 | ✅ running |
| postgres | 5432 | ✅ running |
| redis | 6379 | ✅ running |
| rabbitmq | 5672/15672 | ✅ running |
| litellm | 4000 | ✅ running |

### 访问地址
- Web UI: http://localhost/
- MCP API: http://localhost:8001
- API 文档: http://localhost:8001/docs
- RabbitMQ: http://localhost:15672 (guest/guest)

## 遇到的问题及解决方案

### 1. VECTOR 导入错误
**问题**: `ImportError: cannot import name 'VECTOR' from 'sqlalchemy.dialects.postgresql'`

**解决**: 创建自定义 `Vector` 类型，使用 `LargeBinary` 作为底层存储

### 2. SQL 文本查询错误
**问题**: `ArgumentError: Textual SQL expression should be explicitly declared as text()`

**解决**: 使用 `from sqlalchemy import text`，将原生 SQL 包装在 `text()` 中

### 3. Nginx 404 错误
**问题**: 访问 localhost 返回 404

**解决**: 将 Web UI 配置为 default_server，并移除冲突的 server 块

### 4. 数据库字段缺失
**问题**: 新添加的字段在数据库中不存在

**解决**: 使用 ALTER TABLE 添加新列

## 重要记忆永久保存规则

### 自动保护条件
1. **高访问频率**: 访问次数 >= 10 次
2. **高质量语义记忆**: 质量评分 >= 0.8 的语义记忆
3. **程序技能**: 质量评分 >= 0.7 的程序记忆
4. **关键词触发**: 包含 "important", "critical", "key" 且质量 >= 0.6
5. **LLM 评估**: 晋升时 LLM 判断应该标记为重要

### LLM 评估标准
- 核心身份/价值观
- 关键决策
- 重要学习/教训
- 独特专业知识
- 高价值偏好

### 保护来源
- `user`: 用户手动标记
- `llm`: LLM 评估后自动标记
- `high_quality_semantic`: 高质量语义记忆
- `procedural_skill`: 程序技能
- `frequent_access`: 高频访问
- `content_keywords`: 关键词触发

## 后续待办
- [ ] 完善 OpenCode MCP 集成
- [ ] 优化检索性能
- [ ] 添加更多测试用例
- [ ] 完善文档
