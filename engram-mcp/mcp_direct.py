#!/usr/bin/env python3
"""
Direct MCP Server for Engram
Simple wrapper that just runs the MCP server directly
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql+asyncpg://app:postgres_password@localhost:5432/appdb"))
os.environ.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0"))
os.environ.setdefault("RABBITMQ_URL", os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"))
os.environ.setdefault("LITELLM_BASE_URL", os.getenv("LITELLM_BASE_URL", "http://localhost:4000"))
os.environ.setdefault("LITELLM_API_KEY", os.getenv("LITELLM_API_KEY", "litellm_key_123"))
os.environ.setdefault("LITELLM_EMBED_MODEL", os.getenv("LITELLM_EMBED_MODEL", "text-embedding-3-small"))
os.environ.setdefault("LITELLM_CHAT_MODEL", os.getenv("LITELLM_CHAT_MODEL", "gpt-4o-mini"))
os.environ.setdefault("NAMESPACE", os.getenv("NAMESPACE", "default"))

# Import and run the MCP server
from mcp_server import main
import asyncio

if __name__ == "__main__":
    print("🚀 Starting Direct MCP Server...", file=sys.stderr)
    asyncio.run(main())