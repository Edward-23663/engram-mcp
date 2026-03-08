from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.memory import get_db
from app.schemas.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    TopicCreate,
    TopicResponse,
    TriggerRuleCreate,
    TriggerRuleResponse,
    ResumeResponse,
    StatsResponse,
)
from app.services.memory import MemoryService, TopicService, TriggerService
from app.services.search import SearchService
from app.core.rabbitmq import rabbitmq_client
from app.core.config import get_settings
import time

router = APIRouter(prefix="/api/v1")
settings = get_settings()


# ==================== Memory Routes ====================

@router.post("/memories", response_model=MemoryResponse, status_code=201)
async def create_memory(
    memory_data: MemoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new memory"""
    service = MemoryService(db)
    
    # Store via async queue
    await rabbitmq_client.queue_store(
        namespace=memory_data.context.get("namespace", settings.NAMESPACE),
        memory_id="",  # Will be generated
        content=memory_data.content,
        context=memory_data.context or {},
        tags=memory_data.tags or [],
    )
    
    # Also create directly for immediate response
    memory = await service.create_memory(
        content=memory_data.content,
        namespace=memory_data.context.get("namespace", settings.NAMESPACE),
        context=memory_data.context or {},
        tags=memory_data.tags or [],
        memory_type=memory_data.memory_type,
        source_type=memory_data.source_type or "api",
        source_id=memory_data.source_id,
    )
    
    # Queue classification
    await rabbitmq_client.queue_classify(
        settings.NAMESPACE,
        memory.id,
        memory.content,
    )
    
    return memory


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Get a memory by ID"""
    service = MemoryService(db)
    memory = await service.get_memory(memory_id, namespace)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return memory


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    memory_data: MemoryUpdate,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Update a memory"""
    service = MemoryService(db)
    memory = await service.update_memory(memory_id, **memory_data.model_dump(exclude_none=True))
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return memory


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory"""
    service = MemoryService(db)
    success = await service.delete_memory(memory_id, namespace)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "deleted"}


@router.post("/memories/{memory_id}/mark-important")
async def mark_memory_important(
    memory_id: str,
    reason: str = Query(...),
    source: str = Query("user"),
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Mark a memory as permanently important"""
    service = MemoryService(db)
    success = await service.mark_important(memory_id, reason, source)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "marked_important", "memory_id": memory_id}


@router.post("/memories/{memory_id}/unmark-important")
async def unmark_memory_important(
    memory_id: str,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Unmark a memory as important (only for user-marked)"""
    service = MemoryService(db)
    success = await service.unmark_important(memory_id)
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Cannot unmark: memory is auto-protected or not marked as important"
        )
    
    return {"status": "unmarked", "memory_id": memory_id}


@router.get("/memories/important")
async def get_important_memories(
    namespace: str = Query("default"),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    """Get all important memories"""
    service = MemoryService(db)
    memories = await service.get_important_memories(namespace, limit)
    return memories


@router.post("/memories/{memory_id}/promote")
async def promote_memory(
    memory_id: str,
    target_layer: str = Query(..., regex="^(working|core)$"),
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Promote a memory to a higher layer"""
    service = MemoryService(db)
    success = await service.promote_memory(memory_id, target_layer)
    
    if not success:
        raise HTTPException(status_code=400, detail="Memory promotion rejected by LLM gatekeeper")
    
    return {"status": "promoted", "memory_id": memory_id, "layer": target_layer}
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "deleted", "memory_id": memory_id}


# ==================== Search Routes ====================

@router.post("/memories/search", response_model=MemorySearchResponse)
async def search_memories(
    search_data: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Search memories"""
    service = SearchService(db)
    
    start_time = time.time()
    memories, scores = await service.search(
        query=search_data.query,
        namespace=search_data.namespace or settings.NAMESPACE,
        memory_types=search_data.memory_types or [],
        layers=search_data.layers or [],
        topic_id=search_data.topic_id,
        limit=search_data.limit or 10,
        min_importance=search_data.min_importance,
        min_quality=search_data.min_quality,
        is_important_only=search_data.is_important_only or False,
    )
    query_time = int((time.time() - start_time) * 1000)
    
    # Log access
    memory_service = MemoryService(db)
    for memory in memories:
        await memory_service.log_access(
            namespace=search_data.namespace or settings.NAMESPACE,
            memory_id=memory.id,
            access_type="search",
            query=search_data.query,
            result_count=len(memories),
            latency_ms=query_time,
        )
    
    return MemorySearchResponse(
        results=memories,
        scores=scores,
        total=len(memories),
        query_time_ms=query_time,
    )


@router.get("/memories/search/similar/{memory_id}")
async def get_similar_memories(
    memory_id: str,
    namespace: str = Query("default"),
    limit: int = Query(10),
    db: AsyncSession = Depends(get_db),
):
    """Get similar memories"""
    service = SearchService(db)
    
    similar = await service.find_similar_memories(
        memory_id=memory_id,
        namespace=namespace,
        limit=limit,
    )
    
    return [
        {"memory": m, "similarity": s}
        for m, s in similar
    ]


# ==================== Topic Routes ====================

@router.post("/topics", response_model=TopicResponse, status_code=201)
async def create_topic(
    topic_data: TopicCreate,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new topic"""
    service = TopicService(db)
    
    topic = await service.create_topic(
        name=topic_data.name,
        namespace=namespace,
        description=topic_data.description,
        parent_id=topic_data.parent_id,
    )
    
    return topic


@router.get("/topics", response_model=list[TopicResponse])
async def get_topics(
    namespace: str = Query("default"),
    parent_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get topics"""
    service = TopicService(db)
    topics = await service.get_topics(namespace, parent_id)
    
    return topics


@router.get("/topics/{topic_id}/memories")
async def get_topic_memories(
    topic_id: str,
    namespace: str = Query("default"),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    """Get memories in a topic"""
    service = SearchService(db)
    memories = await service.search_by_topic(topic_id, namespace, limit)
    
    return memories


# ==================== Trigger Routes ====================

@router.post("/triggers", response_model=TriggerRuleResponse, status_code=201)
async def create_trigger(
    trigger_data: TriggerRuleCreate,
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Create a trigger rule"""
    service = TriggerService(db)
    
    trigger = await service.create_trigger(
        name=trigger_data.name,
        trigger_tag=trigger_data.trigger_tag,
        namespace=namespace,
        query_text=trigger_data.query_text,
        memory_types=trigger_data.memory_types or [],
        layers=trigger_data.layers or [],
        limit=trigger_data.limit or 10,
        action_type=trigger_data.action_type or "recall",
        response_format=trigger_data.response_format or "default",
    )
    
    return trigger


@router.get("/triggers", response_model=list[TriggerRuleResponse])
async def get_triggers(
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Get all triggers"""
    service = TriggerService(db)
    triggers = await service.get_all_triggers(namespace)
    
    return triggers


@router.post("/triggers/{trigger_tag}/fire")
async def fire_trigger(
    trigger_tag: str,
    namespace: str = Query("default"),
    context: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """Fire a trigger"""
    await rabbitmq_client.queue_trigger(namespace, trigger_tag, context)
    
    # Also process immediately
    service = SearchService(db)
    trigger_service = TriggerService(db)
    
    trigger = await trigger_service.get_trigger_by_tag(trigger_tag, namespace)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    memories, scores = await service.search(
        query=trigger.query_text or trigger_tag,
        namespace=namespace,
        memory_types=trigger.memory_types,
        layers=trigger.layers,
        limit=trigger.limit,
    )
    
    return {
        "trigger": trigger_tag,
        "results": memories,
        "scores": scores,
    }


# ==================== Resume Route (engram-rs compatible) ====================

@router.get("/resume", response_model=ResumeResponse)
async def resume_session(
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Resume session - get core, recent, topics, and triggers"""
    memory_service = MemoryService(db)
    topic_service = TopicService(db)
    trigger_service = TriggerService(db)
    
    core = await memory_service.get_core_memories(namespace, limit=100)
    recent = await memory_service.get_recent_memories(namespace, limit=50)
    topics = await topic_service.get_topics(namespace)
    triggers = await trigger_service.get_all_triggers(namespace)
    
    return ResumeResponse(
        core=core,
        recent=recent,
        topics=topics,
        triggers=triggers,
    )


# ==================== Stats Route ====================

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    namespace: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Get memory statistics"""
    memory_service = MemoryService(db)
    
    counts = await memory_service.get_memory_count(namespace)
    
    # Get topics count
    topic_result = await db.execute(
        text(f"SELECT COUNT(*) FROM topics WHERE namespace = '{namespace}'")
    )
    topics_count = topic_result.scalar() or 0
    
    # Get archived count
    archived_result = await db.execute(
        text(f"SELECT COUNT(*) FROM archived_memories WHERE namespace = '{namespace}'")
    )
    archived_count = archived_result.scalar() or 0
    
    return StatsResponse(
        total_memories=counts["total"],
        by_layer=counts["by_layer"],
        by_type=counts["by_type"],
        topics_count=topics_count,
        archived_count=archived_count,
    )
