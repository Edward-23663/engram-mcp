#!/bin/bash

set -e

echo "========================================"
echo "Engram MCP 本地部署脚本"
echo "========================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "项目目录: $PROJECT_DIR"

check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "错误: 需要安装 $1"
        exit 1
    fi
}

echo "检查依赖..."
check_command python3
check_command pip3
check_command docker
check_command docker-compose

echo ""
echo "请选择部署模式:"
echo "1) Docker 部署 (推荐)"
echo "2) 本地裸跑"
read -p "请输入选项 [1]: " mode
mode=${mode:-1}

if [ "$mode" = "1" ]; then
    echo ""
    echo "开始 Docker 部署..."
    
    cd "$PROJECT_DIR"
    
    if [ ! -f .env ]; then
        echo "创建环境配置文件..."
        cp engram-mcp/.env.example .env 2>/dev/null || echo "请手动创建 .env 文件"
    fi
    
    echo "启动 Docker 服务..."
    docker-compose up -d
    
    echo ""
    echo "等待服务启动..."
    sleep 10
    
    echo ""
    echo "检查服务状态..."
    docker-compose ps
    
    echo ""
    echo "========================================"
    echo "部署完成!"
    echo "========================================"
    echo "访问以下地址:"
    echo "  - Web UI: http://localhost/"
    echo "  - MCP API: http://localhost:8001"
    echo "  - RabbitMQ: http://localhost:15672"
    echo "  - LiteLLM: http://localhost:4000"
    echo ""
    echo "日志查看:"
    echo "  docker-compose logs -f engram-mcp"
    echo ""
    echo "停止服务:"
    echo "  docker-compose down"

elif [ "$mode" = "2" ]; then
    echo ""
    echo "开始本地裸跑部署..."
    
    echo "安装 Python 依赖..."
    cd "$PROJECT_DIR/engram-mcp"
    pip3 install -r requirements.txt
    
    if [ ! -f .env ]; then
        echo "创建环境配置文件..."
        cp .env.example .env
    fi
    
    echo ""
    echo "请确认以下服务正在运行:"
    echo "  - PostgreSQL (端口 5432)"
    echo "  - Redis (端口 6379)"
    echo "  - RabbitMQ (端口 5672)"
    echo "  - LiteLLM (端口 4000)"
    echo ""
    read -p "确认以上服务已启动? [y/N]: " confirm
    confirm=${confirm:-n}
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "请先启动所需服务后重试"
        exit 1
    fi
    
    echo ""
    echo "启动 Engram MCP..."
    export PYTHONPATH="$PROJECT_DIR/engram-mcp:$PYTHONPATH"
    python3 main.py
fi
