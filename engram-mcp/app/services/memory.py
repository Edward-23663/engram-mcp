from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from app.models.memory import Memory, Topic, ArchivedMemory, TriggerRule, AccessLog
from app.services.llm import llm_service
from app.core.redis import redis_client
from app.core.config import get_settings
from typing import List, Optional
import uuid
import math
from datetime import datetime, timedelta

settings = get_settings()


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_memory(
        self,
        content: str,
        namespace: str = "default",
        context: dict = {},
        tags: list = [],
        memory_type: str = "semantic",
        source_type: str = "manual",
        source_id: str = None,
    ) -> Memory:
        """Create a new memory in Buffer layer"""
        
        # Get embedding
        try:
            embedding = await llm_service.get_embedding(content)
        except Exception as e:
            print(f"Failed to get embedding: {e}")
            embedding = None
        
        memory = Memory(
            id=str(uuid.uuid4()),
            namespace=namespace,
            content=content,
            context=context,
            tags=tags,
            memory_type=memory_type,
            layer="buffer",
            activation_score=1.0,
            decay_score=1.0,
            embedding=embedding,
            source_type=source_type,
            source_id=source_id,
        )
        
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        
        # Update Redis cache
        await redis_client.cache_memory(memory.id, {
            "content": content,
            "layer": "buffer",
            "namespace": namespace,
        })
        
        return memory
    
    async def get_memory(self, memory_id: str, namespace: str = "default") -> Optional[Memory]:
        """Get a memory by ID"""
        # Try cache first
        cached = await redis_client.get_cached_memory(memory_id)
        if cached:
            result = await self.db.execute(
                select(Memory).where(
                    and_(Memory.id == memory_id, Memory.namespace == namespace, Memory.is_deleted == False)
                )
            )
            return result.scalar_one_or_none()
        
        result = await self.db.execute(
            select(Memory).where(
                and_(Memory.id == memory_id, Memory.namespace == namespace, Memory.is_deleted == False)
            )
        )
        return result.scalar_one_or_none()
    
    async def update_memory(self, memory_id: str, **kwargs) -> Optional[Memory]:
        """Update a memory"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return None
        
        for key, value in kwargs.items():
            if hasattr(memory, key):
                setattr(memory, key, value)
        
        memory.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(memory)
        
        # Invalidate cache
        await redis_client.delete_cached_memory(memory_id)
        
        return memory
    
    async def delete_memory(self, memory_id: str, namespace: str = "default", soft: bool = True) -> bool:
        """Delete a memory"""
        memory = await self.get_memory(memory_id, namespace)
        if not memory:
            return False
        
        if soft:
            memory.is_deleted = True
        else:
            await self.db.delete(memory)
        
        await self.db.commit()
        await redis_client.delete_cached_memory(memory_id)
        
        return True
    
    async def get_memories_by_layer(self, namespace: str, layer: str, limit: int = 100) -> List[Memory]:
        """Get memories by layer"""
        result = await self.db.execute(
            select(Memory)
            .where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer == layer,
                    Memory.is_deleted == False,
                )
            )
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_memories_by_type(self, namespace: str, memory_type: str, limit: int = 100) -> List[Memory]:
        """Get memories by type"""
        result = await self.db.execute(
            select(Memory)
            .where(
                and_(
                    Memory.namespace == namespace,
                    Memory.memory_type == memory_type,
                    Memory.is_deleted == False,
                )
            )
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent_memories(self, namespace: str, limit: int = 50) -> List[Memory]:
        """Get recent memories (Buffer + Working)"""
        result = await self.db.execute(
            select(Memory)
            .where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer.in_(["buffer", "working"]),
                    Memory.is_deleted == False,
                )
            )
            .order_by(Memory.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_core_memories(self, namespace: str, limit: int = 100) -> List[Memory]:
        """Get Core layer memories"""
        result = await self.db.execute(
            select(Memory)
            .where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer == "core",
                    Memory.is_deleted == False,
                )
            )
            .order_by(Memory.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def promote_memory(self, memory_id: str, target_layer: str) -> bool:
        """Promote memory to a higher layer"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        old_layer = memory.layer
        memory.layer = target_layer
        
        # Re-evaluate with LLM for promotions
        if target_layer == "working":
            should_promote = await llm_service.should_promote_to_working(memory.content, memory.context or {})
            if not should_promote:
                return False
        
        elif target_layer == "core":
            if not memory.quality_score:
                memory.quality_score = await llm_service.evaluate_quality(memory.content)
            should_promote = await llm_service.should_promote_to_core(
                memory.content, memory.context or {}, memory.quality_score
            )
            if not should_promote:
                return False
            
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
                if not memory.importance_score:
                    memory.importance_score = max(memory.quality_score, 0.8)
        
        await self.db.commit()
        await self.db.refresh(memory)
        
        # Invalidate Redis cache
        await redis_client.delete_cached_memory(memory_id)
        
        print(f"Promoted memory {memory_id} from {old_layer} to {target_layer}")
        return True
    
    async def mark_important(self, memory_id: str, reason: str, source: str = "user") -> bool:
        """Mark a memory as permanently important"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        memory.is_important = True
        memory.importance_reason = reason
        memory.is_auto_protected = (source != "user")
        memory.protection_source = source
        memory.layer = "core"
        
        if not memory.importance_score:
            memory.importance_score = 0.9
        
        await self.db.commit()
        await redis_client.delete_cached_memory(memory_id)
        print(f"Marked memory {memory_id} as important: {reason}")
        return True
    
    async def unmark_important(self, memory_id: str) -> bool:
        """Unmark a memory as important (only for user-marked)"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        if memory.protection_source == "user" or memory.protection_source is None:
            memory.is_important = False
            memory.importance_reason = None
            memory.is_auto_protected = False
            memory.protection_source = None
            await self.db.commit()
            await redis_client.delete_cached_memory(memory_id)
            print(f"Unmarked memory {memory_id} as important")
            return True
        
        return False
    
    async def check_and_auto_protect(self, memory_id: str) -> bool:
        """Check and auto-protect memories based on patterns"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        if memory.is_important or memory.is_auto_protected:
            return True
        
        should_protect, source = await llm_service.detect_auto_protection(
            memory.content,
            memory.access_count,
            memory.quality_score or 0.5,
            memory.memory_type
        )
        
        if should_protect:
            memory.is_auto_protected = True
            memory.protection_source = source
            if not memory.importance_score:
                memory.importance_score = 0.7
            await self.db.commit()
            await redis_client.delete_cached_memory(memory_id)
            print(f"Auto-protected memory {memory_id}: {source}")
            return True
        
        return False
    
    async def archive_memory(self, memory_id: str, reason: str) -> bool:
        """Archive a memory before deletion - respects important memories"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        if memory.is_important or memory.is_auto_protected:
            print(f"Skipping archive - memory {memory_id} is protected")
            return False
        
        archived = ArchivedMemory(
            id=str(uuid.uuid4()),
            original_id=memory.id,
            namespace=memory.namespace,
            content=memory.content,
            context=memory.context,
            tags=memory.tags,
            memory_type=memory.memory_type,
            layer=memory.layer,
            reason=reason,
        )
        
        self.db.add(archived)
        await self.db.delete(memory)
        await self.db.commit()
        
        await redis_client.delete_cached_memory(memory_id)
        return True
    
    async def get_memory_count(self, namespace: str) -> dict:
        """Get memory counts by layer and type"""
        result = await self.db.execute(
            select(Memory.layer, Memory.memory_type, func.count(Memory.id))
            .where(and_(Memory.namespace == namespace, Memory.is_deleted == False))
            .group_by(Memory.layer, Memory.memory_type)
        )
        
        counts = {"by_layer": {}, "by_type": {}, "total": 0}
        for row in result:
            layer, mtype, count = row
            counts["by_layer"][layer] = counts["by_layer"].get(layer, 0) + count
            counts["by_type"][mtype] = counts["by_type"].get(mtype, 0) + count
            counts["total"] += count
        
        return counts
    
    async def get_important_memories(self, namespace: str, limit: int = 50) -> List[Memory]:
        """Get all important memories"""
        result = await self.db.execute(
            select(Memory)
            .where(and_(
                Memory.namespace == namespace,
                Memory.is_deleted == False,
                Memory.is_important == True,
            ))
            .order_by(Memory.importance_score.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def log_access(
        self,
        namespace: str,
        memory_id: str,
        access_type: str,
        query: str = None,
        result_count: int = 0,
        latency_ms: int = 0,
    ):
        """Log memory access"""
        log = AccessLog(
            namespace=namespace,
            memory_id=memory_id,
            access_type=access_type,
            query=query,
            result_count=result_count,
            latency_ms=latency_ms,
        )
        self.db.add(log)
        await self.db.commit()
        
        # Increment activation
        await redis_client.increment_activation(memory_id)


class TopicService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_topic(
        self,
        name: str,
        namespace: str = "default",
        description: str = None,
        parent_id: str = None,
    ) -> Topic:
        """Create a new topic"""
        topic = Topic(
            id=str(uuid.uuid4()),
            namespace=namespace,
            name=name,
            description=description,
            parent_id=parent_id,
        )
        
        self.db.add(topic)
        await self.db.commit()
        await self.db.refresh(topic)
        
        return topic
    
    async def get_topic(self, topic_id: str) -> Optional[Topic]:
        """Get topic by ID"""
        result = await self.db.execute(
            select(Topic).where(Topic.id == topic_id)
        )
        return result.scalar_one_or_none()
    
    async def get_topics(self, namespace: str, parent_id: str = None) -> List[Topic]:
        """Get topics by namespace and parent"""
        query = select(Topic).where(Topic.namespace == namespace)
        if parent_id:
            query = query.where(Topic.parent_id == parent_id)
        else:
            query = query.where(Topic.parent_id == None)
        
        result = await self.db.execute(query.order_by(Topic.memory_count.desc()))
        return list(result.scalars().all())
    
    async def update_topic_stats(self, topic_id: str):
        """Update topic memory count and avg quality"""
        topic = await self.get_topic(topic_id)
        if not topic:
            return
        
        result = await self.db.execute(
            select(
                func.count(Memory.id),
                func.avg(Memory.quality_score)
            )
            .where(
                and_(
                    Memory.topic_id == topic_id,
                    Memory.is_deleted == False,
                )
            )
        )
        count, avg_quality = result.one()
        
        topic.memory_count = count or 0
        topic.avg_quality = float(avg_quality) if avg_quality else None
        
        await self.db.commit()
    
    async def assign_memory_to_topic(self, memory_id: str, topic_id: str) -> bool:
        """Assign a memory to a topic"""
        result = await self.db.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        
        memory.topic_id = topic_id
        await self.db.commit()
        
        # Update topic stats
        await self.update_topic_stats(topic_id)
        
        return True


class TriggerService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_trigger(
        self,
        name: str,
        trigger_tag: str,
        namespace: str = "default",
        query_text: str = None,
        memory_types: list = [],
        layers: list = [],
        limit: int = 10,
        action_type: str = "recall",
        response_format: str = "default",
    ) -> TriggerRule:
        """Create a trigger rule"""
        trigger = TriggerRule(
            id=str(uuid.uuid4()),
            namespace=namespace,
            name=name,
            trigger_tag=trigger_tag,
            query_text=query_text,
            memory_types=memory_types,
            layers=layers,
            limit=limit,
            action_type=action_type,
            response_format=response_format,
        )
        
        self.db.add(trigger)
        await self.db.commit()
        await self.db.refresh(trigger)
        
        return trigger
    
    async def get_trigger_by_tag(self, trigger_tag: str, namespace: str = "default") -> Optional[TriggerRule]:
        """Get trigger by tag"""
        result = await self.db.execute(
            select(TriggerRule).where(
                and_(
                    TriggerRule.trigger_tag == trigger_tag,
                    TriggerRule.namespace == namespace,
                    TriggerRule.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_all_triggers(self, namespace: str = "default") -> List[TriggerRule]:
        """Get all triggers for namespace"""
        result = await self.db.execute(
            select(TriggerRule).where(
                and_(
                    TriggerRule.namespace == namespace,
                    TriggerRule.is_active == True,
                )
            )
        )
        return list(result.scalars().all())
