"""
MCP (Model Context Protocol) Adapter for OpenCode integration
Compatible with OpenCode MCP calling conventions
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.models.memory import get_db, AsyncSessionLocal
from app.services.memory import MemoryService, TopicService, TriggerService
from app.services.search import SearchService
from app.core.rabbitmq import rabbitmq_client
from app.core.config import get_settings

settings = get_settings()


class MCPRequest(BaseModel):
    method: str
    params: Dict[str, Any] = {}
    namespace: str = "default"


class MCPResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None


class MCPAdapter:
    """MCP Adapter for memory operations"""
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """Handle MCP request"""
        method = request.method
        params = request.params
        namespace = request.namespace or settings.NAMESPACE
        
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
            else:
                return MCPResponse(
                    success=False,
                    error=f"Unknown method: {method}"
                )
        except Exception as e:
            return MCPResponse(success=False, error=str(e))
    
    async def _create_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Create memory via MCP"""
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            
            memory = await service.create_memory(
                content=params.get("content", ""),
                namespace=namespace,
                context=params.get("context", {}),
                tags=params.get("tags", []),
                source_type=params.get("source_type", "mcp"),
            )
            
            # Queue for classification
            await rabbitmq_client.queue_classify(namespace, memory.id, memory.content)
            
            return MCPResponse(success=True, data={
                "id": memory.id,
                "content": memory.content,
                "layer": memory.layer,
            })
    
    async def _get_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Get memory via MCP"""
        memory_id = params.get("id")
        if not memory_id:
            return MCPResponse(success=False, error="Missing memory id")
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            memory = await service.get_memory(memory_id, namespace)
            
            if not memory:
                return MCPResponse(success=False, error="Memory not found")
            
            return MCPResponse(success=True, data={
                "id": memory.id,
                "content": memory.content,
                "layer": memory.layer,
                "memory_type": memory.memory_type,
                "tags": memory.tags,
                "context": memory.context,
            })
    
    async def _search_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Search memories via MCP"""
        query = params.get("query", "")
        limit = params.get("limit", 10)
        
        async with AsyncSessionLocal() as db:
            service = SearchService(db)
            
            memories, scores = await service.search(
                query=query,
                namespace=namespace,
                memory_types=params.get("types", []),
                layers=params.get("layers", []),
                limit=limit,
            )
            
            return MCPResponse(success=True, data={
                "results": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "layer": m.layer,
                        "type": m.memory_type,
                        "score": s,
                    }
                    for m, s in zip(memories, scores)
                ],
                "total": len(memories),
            })
    
    async def _update_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Update memory via MCP"""
        memory_id = params.get("id")
        if not memory_id:
            return MCPResponse(success=False, error="Missing memory id")
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            
            update_data = {k: v for k, v in params.items() if k not in ["id", "namespace"]}
            memory = await service.update_memory(memory_id, **update_data)
            
            if not memory:
                return MCPResponse(success=False, error="Memory not found")
            
            return MCPResponse(success=True, data={"id": memory.id})
    
    async def _delete_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Delete memory via MCP"""
        memory_id = params.get("id")
        if not memory_id:
            return MCPResponse(success=False, error="Missing memory id")
        
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            success = await service.delete_memory(memory_id, namespace)
            
            if not success:
                return MCPResponse(success=False, error="Memory not found")
            
            return MCPResponse(success=True, data={"deleted": True})
    
    async def _recall_memory(self, params: Dict, namespace: str) -> MCPResponse:
        """Recall memories via MCP (uses trigger or query)"""
        async with AsyncSessionLocal() as db:
            service = SearchService(db)
            trigger_tag = params.get("trigger")
            
            if trigger_tag:
                # Use trigger
                trigger_service = TriggerService(db)
                trigger = await trigger_service.get_trigger_by_tag(trigger_tag, namespace)
                
                if trigger:
                    memories, scores = await service.search(
                        query=trigger.query_text or trigger_tag,
                        namespace=namespace,
                        memory_types=trigger.memory_types,
                        layers=trigger.layers,
                        limit=trigger.limit,
                    )
                else:
                    return MCPResponse(success=False, error=f"Trigger not found: {trigger_tag}")
            else:
                # Use query
                query = params.get("query", "")
                memories, scores = await service.search(
                    query=query,
                    namespace=namespace,
                    limit=params.get("limit", 10),
                )
            
            return MCPResponse(success=True, data={
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "layer": m.layer,
                        "type": m.memory_type,
                        "score": s,
                    }
                    for m, s in zip(memories, scores)
                ],
                "total": len(memories),
            })
    
    async def _list_topics(self, params: Dict, namespace: str) -> MCPResponse:
        """List topics via MCP"""
        async with AsyncSessionLocal() as db:
            service = TopicService(db)
            topics = await service.get_topics(namespace)
            
            return MCPResponse(success=True, data={
                "topics": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description,
                        "memory_count": t.memory_count,
                    }
                    for t in topics
                ]
            })
    
    async def _get_topic(self, params: Dict, namespace: str) -> MCPResponse:
        """Get topic via MCP"""
        topic_id = params.get("id")
        if not topic_id:
            return MCPResponse(success=False, error="Missing topic id")
        
        async with AsyncSessionLocal() as db:
            service = TopicService(db)
            topic = await service.get_topic(topic_id)
            
            if not topic:
                return MCPResponse(success=False, error="Topic not found")
            
            return MCPResponse(success=True, data={
                "id": topic.id,
                "name": topic.name,
                "description": topic.description,
                "memory_count": topic.memory_count,
                "summary": topic.summary,
            })
    
    async def _fire_trigger(self, params: Dict, namespace: str) -> MCPResponse:
        """Fire trigger via MCP"""
        trigger_tag = params.get("tag")
        if not trigger_tag:
            return MCPResponse(success=False, error="Missing trigger tag")
        
        # Queue trigger
        await rabbitmq_client.queue_trigger(namespace, trigger_tag, params.get("context", {}))
        
        # Process immediately
        async with AsyncSessionLocal() as db:
            service = SearchService(db)
            trigger_service = TriggerService(db)
            
            trigger = await trigger_service.get_trigger_by_tag(trigger_tag, namespace)
            if not trigger:
                return MCPResponse(success=False, error=f"Trigger not found: {trigger_tag}")
            
            memories, scores = await service.search(
                query=trigger.query_text or trigger_tag,
                namespace=namespace,
                memory_types=trigger.memory_types,
                layers=trigger.layers,
                limit=trigger.limit,
            )
            
            return MCPResponse(success=True, data={
                "trigger": trigger_tag,
                "results": [
                    {"id": m.id, "content": m.content, "score": s}
                    for m, s in zip(memories, scores)
                ],
            })
    
    async def _list_triggers(self, params: Dict, namespace: str) -> MCPResponse:
        """List triggers via MCP"""
        async with AsyncSessionLocal() as db:
            service = TriggerService(db)
            triggers = await service.get_all_triggers(namespace)
            
            return MCPResponse(success=True, data={
                "triggers": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "tag": t.trigger_tag,
                        "action_type": t.action_type,
                    }
                    for t in triggers
                ]
            })
    
    async def _resume_session(self, params: Dict, namespace: str) -> MCPResponse:
        """Resume session via MCP"""
        async with AsyncSessionLocal() as db:
            memory_service = MemoryService(db)
            topic_service = TopicService(db)
            trigger_service = TriggerService(db)
            
            core = await memory_service.get_core_memories(namespace, limit=50)
            recent = await memory_service.get_recent_memories(namespace, limit=30)
            topics = await topic_service.get_topics(namespace)
            triggers = await trigger_service.get_all_triggers(namespace)
            
            return MCPResponse(success=True, data={
                "core": [
                    {"id": m.id, "content": m.content, "type": m.memory_type}
                    for m in core
                ],
                "recent": [
                    {"id": m.id, "content": m.content, "layer": m.layer}
                    for m in recent
                ],
                "topics": [{"id": t.id, "name": t.name} for t in topics],
                "triggers": [{"tag": t.trigger_tag, "name": t.name} for t in triggers],
            })
    
    async def _get_stats(self, params: Dict, namespace: str) -> MCPResponse:
        """Get stats via MCP"""
        async with AsyncSessionLocal() as db:
            service = MemoryService(db)
            counts = await service.get_memory_count(namespace)
            
            return MCPResponse(success=True, data=counts)


mcp_adapter = MCPAdapter()
