#!/usr/bin/env python3
"""
MCP (Model Context Protocol) Server for Engram
This server communicates via stdio using JSON-RPC protocol
Compatible with OpenCode MCP calling conventions
"""
import sys
import json
import asyncio
import os
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment before importing app modules
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql+asyncpg://app:postgres_password@localhost:5432/appdb"))
os.environ.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0"))
os.environ.setdefault("RABBITMQ_URL", os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"))
os.environ.setdefault("LITELLM_BASE_URL", os.getenv("LITELLM_BASE_URL", "http://localhost:4000"))
os.environ.setdefault("LITELLM_API_KEY", os.getenv("LITELLM_API_KEY", "litellm_key_123"))
os.environ.setdefault("LITELLM_EMBED_MODEL", os.getenv("LITELLM_EMBED_MODEL", "text-embedding-3-small"))
os.environ.setdefault("LITELLM_CHAT_MODEL", os.getenv("LITELLM_CHAT_MODEL", "gpt-4o-mini"))
os.environ.setdefault("NAMESPACE", os.getenv("NAMESPACE", "default"))

from app.models.memory import get_db, AsyncSessionLocal
from app.services.memory import MemoryService, TopicService, TriggerService
from app.services.search import SearchService
from app.core.rabbitmq import rabbitmq_client
from app.core.redis import redis_client
from app.core.config import get_settings

settings = get_settings()


class MCPMethodHandler:
    """Handle MCP method calls"""
    
    async def handle(self, method: str, params: Dict[str, Any], namespace: str) -> Dict:
        """Handle a single MCP method"""
        try:
            if method == "memory.create":
                return await self._create_memory(params, namespace)
            elif method == "memory.get":
                return await self._get_memory(params, namespace)
            elif method == "memory.search":
                return await self._search_memory(params, namespace)
            elif method == "memory.update":
                return await self._update_memory(params, namespace)
            elif method == "memory.delete":
                return await self._delete_memory(params, namespace)
            elif method == "memory.recall":
                return await self._recall_memory(params, namespace)
            elif method == "memory.list":
                return await self._list_memories(params, namespace)
            elif method == "memory.mark_important":
                return await self._mark_important(params, namespace)
            elif method == "memory.get_important":
                return await self._get_important_memories(params, namespace)
            elif method == "topic.list":
                return await self._list_topics(params, namespace)
            elif method == "topic.get":
                return await self._get_topic(params, namespace)
            elif method == "trigger.fire":
                return await self._fire_trigger(params, namespace)
            elif method == "trigger.list":
                return await self._list_triggers(params, namespace)
            elif method == "session.resume":
                return await self._resume_session(params, namespace)
            elif method == "stats.get":
                return await self._get_stats(params, namespace)
            elif method == "tools/list":
                return await self._list_tools()
            elif method == "resources/list":
                return await self._list_resources()
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _create_memory(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            memory = await service.create_memory(
                content=params.get("content", ""),
                namespace=namespace,
                context=params.get("context", {}),
                tags=params.get("tags", []),
                source_type=params.get("source_type", "mcp"),
            )
            try:
                await rabbitmq_client.queue_classify(namespace, memory.id, memory.content)
            except:
                pass
            return {"success": True, "data": {
                "id": memory.id,
                "content": memory.content,
                "layer": memory.layer,
                "memory_type": memory.memory_type,
                "is_important": memory.is_important,
            }}
    
    async def _get_memory(self, params: Dict, namespace: str) -> Dict:
        memory_id = params.get("id")
        if not memory_id:
            return {"success": False, "error": "Missing memory id"}
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            memory = await service.get_memory(memory_id, namespace)
            if not memory:
                return {"success": False, "error": "Memory not found"}
            return {"success": True, "data": {
                "id": memory.id,
                "content": memory.content,
                "layer": memory.layer,
                "memory_type": memory.memory_type,
                "is_important": memory.is_important,
                "importance_score": memory.importance_score,
                "tags": memory.tags,
                "context": memory.context,
            }}
    
    async def _search_memory(self, params: Dict, namespace: str) -> Dict:
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Missing query"}
        
        async with AsyncSessionLocal() as db:
            service = SearchService(db)
            memories, scores = await service.search(
                query=query,
                namespace=namespace,
                memory_types=params.get("memory_types", []),
                layers=params.get("layers", []),
                limit=params.get("limit", 10),
                min_importance=params.get("min_importance"),
                min_quality=params.get("min_quality"),
                is_important_only=params.get("is_important_only", False),
            )
            return {"success": True, "data": {
                "results": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "layer": m.layer,
                        "memory_type": m.memory_type,
                        "score": scores[i] if i < len(scores) else 0,
                        "is_important": m.is_important,
                    }
                    for i, m in enumerate(memories)
                ],
                "total": len(memories),
            }}
    
    async def _update_memory(self, params: Dict, namespace: str) -> Dict:
        memory_id = params.get("id")
        if not memory_id:
            return {"success": False, "error": "Missing memory id"}
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            memory = await service.update_memory(memory_id, **params)
            if not memory:
                return {"success": False, "error": "Memory not found"}
            return {"success": True, "data": {"id": memory.id}}
    
    async def _delete_memory(self, params: Dict, namespace: str) -> Dict:
        memory_id = params.get("id")
        if not memory_id:
            return {"success": False, "error": "Missing memory id"}
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            success = await service.delete_memory(memory_id, namespace)
            return {"success": success}
    
    async def _recall_memory(self, params: Dict, namespace: str) -> Dict:
        return await self._search_memory(params, namespace)
    
    async def _list_memories(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            limit = params.get("limit", 50)
            layer = params.get("layer")
            if layer:
                memories = await service.get_memories_by_layer(namespace, layer, limit)
            else:
                memories = await service.get_recent_memories(namespace, limit)
            return {"success": True, "data": {
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "layer": m.layer,
                        "memory_type": m.memory_type,
                    }
                    for m in memories
                ]
            }}
    
    async def _mark_important(self, params: Dict, namespace: str) -> Dict:
        memory_id = params.get("id")
        reason = params.get("reason", "user_marked")
        
        if not memory_id:
            return {"success": False, "error": "Missing memory id"}
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            success = await service.mark_important(memory_id, reason, "user")
            return {"success": success, "data": {"id": memory_id}}
    
    async def _get_important_memories(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            limit = params.get("limit", 50)
            memories = await service.get_important_memories(namespace, limit)
            return {"success": True, "data": {
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "layer": m.layer,
                        "importance_reason": m.importance_reason,
                    }
                    for m in memories
                ]
            }}
    
    async def _list_topics(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = TopicService(db)
            topics = await service.get_topics(namespace)
            return {"success": True, "data": {
                "topics": [
                    {"id": t.id, "name": t.name, "memory_count": t.memory_count}
                    for t in topics
                ]
            }}
    
    async def _get_topic(self, params: Dict, namespace: str) -> Dict:
        topic_id = params.get("id")
        if not topic_id:
            return {"success": False, "error": "Missing topic id"}
        
        async with AsyncSessionLocal() as db:
            service = TopicService(db)
            topic = await service.get_topic(topic_id)
            if not topic:
                return {"success": False, "error": "Topic not found"}
            return {"success": True, "data": {
                "id": topic.id,
                "name": topic.name,
                "description": topic.description,
                "memory_count": topic.memory_count,
            }}
    
    async def _fire_trigger(self, params: Dict, namespace: str) -> Dict:
        trigger_id = params.get("id")
        trigger_tag = params.get("trigger_tag")
        
        async with AsyncSessionLocal() as db:
            trigger_service = TriggerService(db)
            search_service = SearchService(db)
            
            if trigger_id:
                # Get trigger by ID - need to iterate since there's no get_trigger method
                triggers = await trigger_service.get_all_triggers(namespace)
                trigger = next((t for t in triggers if t.id == trigger_id), None)
            elif trigger_tag:
                trigger = await trigger_service.get_trigger_by_tag(trigger_tag, namespace)
            else:
                return {"success": False, "error": "Missing trigger id or tag"}
            
            if not trigger:
                return {"success": False, "error": "Trigger not found"}
            
            query = trigger.query_text if trigger.query_text else trigger_tag
            memories, scores = await search_service.search(
                query=query,
                namespace=namespace,
                memory_types=trigger.memory_types or [],
                layers=trigger.layers or [],
                limit=trigger.limit,
            )
            return {"success": True, "data": {
                "trigger": {"id": trigger.id, "name": trigger.name, "trigger_tag": trigger.trigger_tag},
                "results": [
                    {"id": m.id, "content": m.content, "layer": m.layer}
                    for m in memories
                ]
            }}
    
    async def _list_triggers(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = TriggerService(db)
            triggers = await service.get_all_triggers(namespace)
            return {"success": True, "data": {
                "triggers": [
                    {"id": t.id, "name": t.name, "trigger_tag": t.trigger_tag, "is_active": t.is_active}
                    for t in triggers
                ]
            }}
    
    async def _resume_session(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            memory_service = MemoryService(db)
            topic_service = TopicService(db)
            trigger_service = TriggerService(db)
            
            core = await memory_service.get_core_memories(namespace)
            recent = await memory_service.get_recent_memories(namespace)
            topics = await topic_service.get_topics(namespace)
            triggers = await trigger_service.get_all_triggers(namespace)
            
            return {"success": True, "data": {
                "core": [{"id": m.id, "content": m.content, "layer": m.layer} for m in core],
                "recent": [{"id": m.id, "content": m.content, "layer": m.layer} for m in recent],
                "topics": [{"id": t.id, "name": t.name} for t in topics],
                "triggers": [{"id": t.id, "name": t.name, "trigger_tag": t.trigger_tag} for t in triggers],
            }}
    
    async def _get_stats(self, params: Dict, namespace: str) -> Dict:
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            counts = await service.get_memory_count(namespace)
            return {"success": True, "data": counts}
    
    async def _list_tools(self) -> Dict:
        return {
            "tools": [
                {"name": "memory.create", "description": "Create a new memory", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "context": {"type": "object"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["content"]}},
                {"name": "memory.get", "description": "Get a memory by ID", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
                {"name": "memory.search", "description": "Search memories", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "namespace": {"type": "string"}, "memory_types": {"type": "array", "items": {"type": "string"}}, "layers": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}}}},
                {"name": "memory.list", "description": "List memories", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}, "layer": {"type": "string"}, "limit": {"type": "integer"}}}},
                {"name": "memory.mark_important", "description": "Mark memory as important", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["id"]}},
                {"name": "memory.get_important", "description": "Get important memories", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}, "limit": {"type": "integer"}}}},
                {"name": "topic.list", "description": "List topics", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}},
                {"name": "topic.get", "description": "Get topic by ID", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
                {"name": "trigger.fire", "description": "Fire a trigger", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "trigger_tag": {"type": "string"}}}},
                {"name": "trigger.list", "description": "List triggers", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}},
                {"name": "session.resume", "description": "Get session resume data", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}},
                {"name": "stats.get", "description": "Get memory statistics", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}},
            ]
        }
    
    async def _list_resources(self) -> Dict:
        return {"success": True, "data": {"resources": []}}


async def init_services():
    """Initialize services"""
    try:
        await redis_client.connect()
    except Exception as e:
        print(f"Warning: Redis not connected: {e}", file=sys.stderr)
    try:
        await rabbitmq_client.connect()
    except Exception as e:
        print(f"Warning: RabbitMQ not connected: {e}", file=sys.stderr)


async def cleanup_services():
    """Cleanup services"""
    try:
        await rabbitmq_client.close()
    except:
        pass


async def process_request(request: Dict) -> Dict:
    """Process a single JSON-RPC request"""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    namespace = params.pop("namespace", "default") if isinstance(params, dict) else "default"
    
    handler = MCPMethodHandler()
    result = await handler.handle(method, params, namespace)
    
    response = {
        "jsonrpc": "2.0",
        "result": result,
        "id": request_id
    }
    return response


async def main():
    """Main MCP server loop"""
    await init_services()
    
    try:
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                request = json.loads(line)
                
                if request.get("method") == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {},
                                "resources": {},
                            },
                            "serverInfo": {
                                "name": "engram-mcp",
                                "version": "1.0.0"
                            }
                        },
                        "id": request.get("id")
                    }
                    print(json.dumps(response), flush=True)
                    continue
                
                response = await process_request(request)
                print(json.dumps(response), flush=True)
                
            except json.JSONDecodeError:
                continue
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": None
                }
                print(json.dumps(error_response), flush=True)
    finally:
        await cleanup_services()


if __name__ == "__main__":
    asyncio.run(main())
