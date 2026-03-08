import asyncio
from app.core.rabbitmq import rabbitmq_client
from app.models.memory import get_db, AsyncSessionLocal
from app.services.memory import MemoryService, TopicService, TriggerService
from app.services.search import DecayService, CleanupService, MergeService
from app.services.llm import llm_service
from app.core.config import get_settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


async def handle_store_message(data: dict):
    """Handle memory store message"""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db)
        
        memory = await memory_service.create_memory(
            content=data["content"],
            namespace=data.get("namespace", "default"),
            context=data.get("context", {}),
            tags=data.get("tags", []),
            source_type=data.get("source_type", "api"),
        )
        
        # Queue for classification
        await rabbitmq_client.queue_classify(
            data.get("namespace", "default"),
            memory.id,
            memory.content,
        )
        
        logger.info(f"Stored memory {memory.id}")


async def handle_classify_message(data: dict):
    """Handle memory classification message"""
    async with AsyncSessionLocal() as db:
        memory_service = MemoryService(db)
        
        memory = await memory_service.get_memory(
            data["memory_id"],
            data.get("namespace", "default")
        )
        
        if not memory:
            return
        
        # Classify memory type using LLM
        memory_type = await llm_service.classify_memory_type(memory.content)
        
        # Evaluate quality
        quality_score = await llm_service.evaluate_quality(memory.content)
        
        await memory_service.update_memory(
            memory.id,
            memory_type=memory_type,
            quality_score=quality_score,
        )
        
        logger.info(f"Classified memory {memory.id} as {memory_type}")


async def handle_decay_message(data: dict):
    """Handle memory decay message"""
    async with AsyncSessionLocal() as db:
        decay_service = DecayService(db)
        
        await decay_service.decay_memories(
            data.get("namespace", "default"),
            data.get("layer", "buffer"),
        )
        
        logger.info(f"Decayed memories in {data.get('namespace')}/{data.get('layer')}")


async def handle_cleanup_message(data: dict):
    """Handle memory cleanup message"""
    async with AsyncSessionLocal() as db:
        cleanup_service = CleanupService(db)
        
        count = await cleanup_service.cleanup_buffer(
            data.get("namespace", "default"),
        )
        
        logger.info(f"Cleaned up {count} memories in {data.get('namespace')}")


async def handle_merge_message(data: dict):
    """Handle memory merge message"""
    async with AsyncSessionLocal() as db:
        merge_service = MergeService(db)
        
        count = await merge_service.find_and_merge_duplicates(
            data.get("namespace", "default"),
        )
        
        logger.info(f"Merged {count} memories in {data.get('namespace')}")


async def handle_trigger_message(data: dict):
    """Handle trigger processing message"""
    async with AsyncSessionLocal() as db:
        trigger_service = TriggerService(db)
        memory_service = MemoryService(db)
        
        trigger_tag = data.get("trigger_tag")
        namespace = data.get("namespace", "default")
        
        trigger = await trigger_service.get_trigger_by_tag(trigger_tag, namespace)
        if not trigger:
            return
        
        # Execute trigger - get memories
        from app.services.search import SearchService
        search_service = SearchService(db)
        
        memories, scores = await search_service.search(
            query=trigger.query_text or trigger_tag,
            namespace=namespace,
            memory_types=trigger.memory_types,
            layers=trigger.layers,
            limit=trigger.limit,
        )
        
        # Update access counts
        for memory in memories:
            await memory_service.log_access(
                namespace=namespace,
                memory_id=memory.id,
                access_type="trigger",
                query=trigger_tag,
                result_count=len(memories),
            )
        
        logger.info(f"Processed trigger {trigger_tag}, found {len(memories)} memories")


async def handle_promotion_message(data: dict):
    """Handle memory promotion message"""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, and_
        from app.models.memory import Memory
        
        namespace = data.get("namespace", "default")
        
        # Promote Buffer -> Working
        buffer_result = await db.execute(
            select(Memory).where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer == "buffer",
                    Memory.is_deleted == False,
                )
            ).order_by(Memory.quality_score.desc().nullslast()).limit(50)
        )
        
        buffer_memories = list(buffer_result.scalars().all())
        
        promoted_count = 0
        for memory in buffer_memories:
            should_promote = await llm_service.should_promote_to_working(
                memory.content, memory.context or {}
            )
            if should_promote:
                memory.layer = "working"
                await db.commit()
                promoted_count += 1
        
        # Promote Working -> Core
        working_result = await db.execute(
            select(Memory).where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer == "working",
                    Memory.is_deleted == False,
                )
            ).order_by(Memory.quality_score.desc().nullslast()).limit(20)
        )
        
        working_memories = list(working_result.scalars().all())
        
        core_promoted = 0
        for memory in working_memories:
            if not memory.quality_score:
                memory.quality_score = await llm_service.evaluate_quality(memory.content)
            
            should_promote = await llm_service.should_promote_to_core(
                memory.content, memory.context or {}, memory.quality_score
            )
            if should_promote:
                memory.layer = "core"
                
                should_mark_important, importance_reason = await llm_service.should_mark_important(
                    memory.content,
                    memory.context or {},
                    memory.quality_score,
                    memory.access_count,
                    memory.memory_type
                )
                
                if should_mark_important:
                    memory.is_important = True
                    memory.importance_reason = importance_reason
                    memory.is_auto_protected = True
                    memory.protection_source = "llm"
                    memory.importance_score = max(memory.quality_score or 0.5, 0.8)
                
                await db.commit()
                core_promoted += 1
        
        logger.info(f"Promotion complete: {promoted_count} buffer->working, {core_promoted} working->core in {namespace}")


async def start_consumers():
    """Start all RabbitMQ consumers"""
    await rabbitmq_client.connect()
    
    # Declare promotion queue
    await rabbitmq_client.channel.declare_queue("engram.memory.promotion", durable=True)
    
    # Start consumers in background tasks
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_MEMORY_STORE,
            handle_store_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_MEMORY_CLASSIFY,
            handle_classify_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_MEMORY_DECAY,
            handle_decay_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_MEMORY_CLEANUP,
            handle_cleanup_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_MEMORY_MERGE,
            handle_merge_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            rabbitmq_client.QUEUE_TRIGGER_PROCESS,
            handle_trigger_message
        )
    )
    
    asyncio.create_task(
        rabbitmq_client.consume(
            "engram.memory.promotion",
            handle_promotion_message
        )
    )
    
    logger.info("All consumers started")
