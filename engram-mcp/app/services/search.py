from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory, Topic
from app.services.llm import llm_service
from app.services.memory import MemoryService, TopicService
from app.core.redis import redis_client
from app.core.config import get_settings
from typing import List, Tuple, Optional
import time
import math

settings = get_settings()


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
        self.topic_service = TopicService(db)
    
    async def search(
        self,
        query: str,
        namespace: str = "default",
        memory_types: List[str] = [],
        layers: List[str] = [],
        topic_id: str = None,
        limit: int = 10,
        min_importance: float = None,
        min_quality: float = None,
        is_important_only: bool = False,
    ) -> Tuple[List[Memory], List[float]]:
        """
        Hybrid search: semantic (vector) + keyword (BM25-like)
        Returns memories and their scores
        """
        start_time = time.time()
        
        # Get query embedding
        try:
            query_embedding = await llm_service.get_embedding(query)
        except Exception as e:
            print(f"Failed to get query embedding: {e}")
            return [], []
        
        # Build base filter conditions
        conditions = [
            Memory.namespace == namespace,
            Memory.is_deleted == False,
            Memory.embedding.isnot(None),
        ]
        
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))
        
        if layers:
            conditions.append(Memory.layer.in_(layers))
        
        if topic_id:
            conditions.append(Memory.topic_id == topic_id)
        
        if min_importance is not None:
            conditions.append(Memory.importance_score >= min_importance)
        
        if min_quality is not None:
            conditions.append(Memory.quality_score >= min_quality)
        
        if is_important_only:
            conditions.append(Memory.is_important == True)
        
        # Vector similarity search (cosine similarity)
        # Using pgvector's cosine distance
        vector_query = select(Memory).where(and_(*conditions)).order_by(
            text(f"embedding <=> '{query_embedding}'")
        ).limit(limit * 2)  # Get more for reranking
        
        vector_result = await self.db.execute(vector_query)
        vector_memories = list(vector_result.scalars().all())
        
        # If we don't have vectors, fall back to keyword search
        if not vector_memories:
            keyword_query = select(Memory).where(
                and_(*conditions, Memory.content.ilike(f"%{query}%"))
            ).limit(limit)
            
            keyword_result = await self.db.execute(keyword_query)
            vector_memories = list(keyword_result.scalars().all())
            scores = [1.0] * len(vector_memories)
        else:
            # Calculate cosine similarity scores
            scores = []
            for memory in vector_memories:
                if memory.embedding:
                    sim = self._cosine_similarity(query_embedding, memory.embedding)
                    scores.append(sim)
                else:
                    scores.append(0.5)
        
        # Apply Sigmoid scoring to differentiate results
        sigmoid_scores = [self._sigmoid(s) for s in scores]
        
        # Layer weighting
        layer_weights = {"core": 1.5, "working": 1.2, "buffer": 1.0}
        weighted_scores = []
        for memory, score in zip(vector_memories, sigmoid_scores):
            weight = layer_weights.get(memory.layer, 1.0)
            # Boost by activation count
            activation = memory.access_count * 0.05
            weighted_scores.append(score * weight + activation)
        
        # Sort by weighted score
        sorted_pairs = sorted(
            zip(vector_memories, weighted_scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Take top results
        final_memories = [m for m, s in sorted_pairs[:limit]]
        final_scores = [s for m, s in sorted_pairs[:limit]]
        
        query_time = int((time.time() - start_time) * 1000)
        
        return final_memories, final_scores
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _sigmoid(self, x: float) -> float:
        """Sigmoid function for score compression"""
        return 1 / (1 + math.exp(-5 * (x - 0.5)))
    
    async def search_by_topic(
        self,
        topic_id: str,
        namespace: str = "default",
        limit: int = 20,
    ) -> List[Memory]:
        """Search memories by topic"""
        topic = await self.topic_service.get_topic(topic_id)
        if not topic:
            return []
        
        result = await self.db.execute(
            select(Memory).where(
                and_(
                    Memory.topic_id == topic_id,
                    Memory.namespace == namespace,
                    Memory.is_deleted == False,
                )
            )
            .order_by(Memory.quality_score.desc().nullslast(), Memory.created_at.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def find_similar_memories(
        self,
        memory_id: str,
        namespace: str = "default",
        threshold: float = None,
        limit: int = 10,
    ) -> List[Tuple[Memory, float]]:
        """Find similar memories using vector similarity"""
        threshold = threshold or settings.SIMILARITY_THRESHOLD
        
        memory = await self.memory_service.get_memory(memory_id, namespace)
        if not memory or not memory.embedding:
            return []
        
        # Find similar memories in same namespace
        result = await self.db.execute(
            select(Memory).where(
                and_(
                    Memory.namespace == namespace,
                    Memory.id != memory_id,
                    Memory.embedding.isnot(None),
                    Memory.is_deleted == False,
                )
            ).limit(limit * 3)
        )
        
        similar_memories = []
        for m in result.scalars().all():
            if m.embedding:
                sim = self._cosine_similarity(memory.embedding, m.embedding)
                if sim >= threshold:
                    similar_memories.append((m, sim))
        
        # Sort by similarity
        similar_memories.sort(key=lambda x: x[1], reverse=True)
        
        return similar_memories[:limit]


class DecayService:
    """Memory decay service based on Ebbinghaus forgetting curve"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
    
    async def decay_memories(self, namespace: str, layer: str):
        """Apply exponential decay to memories in a layer"""
        
        half_lives = {
            "episodic": settings.EPISODIC_HALF_LIFE,
            "semantic": settings.SEMANTIC_HALF_LIFE,
            "procedural": settings.PROCEDURAL_HALF_LIFE,
        }
        
        memories = await self.memory_service.get_memories_by_layer(namespace, layer, limit=500)
        
        for memory in memories:
            if layer == "core":
                continue  # Core layer never decays
            
            # Calculate time since last update
            time_diff = (datetime.utcnow() - memory.updated_at).total_seconds()
            
            # Get half-life for memory type
            half_life = half_lives.get(memory.memory_type, settings.SEMANTIC_HALF_LIFE)
            
            # Exponential decay: decay = 0.5^(time/half_life)
            new_decay = math.pow(0.5, time_diff / half_life)
            
            # Apply activation boost from Redis
            activation_count = await redis_client.get_activation(memory.id)
            activation_boost = min(activation_count * 0.1, 0.5)
            
            # Final decay score
            final_decay = max(new_decay - activation_boost, 0.01)  # Floor at 0.01
            
            memory.decay_score = final_decay
            
            # Check if below threshold (only for buffer)
            if layer == "buffer" and final_decay < settings.DECAY_THRESHOLD:
                # Will be cleaned up by cleanup service
                pass
        
        await self.db.commit()
        print(f"Decayed {len(memories)} memories in {namespace}/{layer}")


class CleanupService:
    """Memory cleanup service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
    
    async def cleanup_buffer(self, namespace: str):
        """Clean up Buffer layer memories below threshold"""
        
        result = await self.db.execute(
            select(Memory).where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer == "buffer",
                    Memory.decay_score < settings.DECAY_THRESHOLD,
                    Memory.is_deleted == False,
                )
            ).limit(100)
        )
        
        memories = list(result.scalars().all())
        
        for memory in memories:
            await self.memory_service.archive_memory(memory.id, "decay_below_threshold")
        
        print(f"Cleaned up {len(memories)} Buffer memories from {namespace}")
        return len(memories)


class MergeService:
    """Memory semantic deduplication service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
        self.search_service = SearchService(db)
    
    async def find_and_merge_duplicates(self, namespace: str, limit: int = 50):
        """Find and merge similar memories"""
        
        result = await self.db.execute(
            select(Memory).where(
                and_(
                    Memory.namespace == namespace,
                    Memory.layer.in_(["buffer", "working"]),
                    Memory.is_deleted == False,
                    Memory.embedding.isnot(None),
                )
            ).limit(limit * 2)
        )
        
        memories = list(result.scalars().all())
        merged_count = 0
        
        processed = set()
        
        for memory in memories:
            if memory.id in processed:
                continue
            
            # Find similar memories
            similar = await self.search_service.find_similar_memories(
                memory.id,
                namespace,
                threshold=settings.SIMILARITY_THRESHOLD,
                limit=5
            )
            
            for similar_memory, score in similar:
                if similar_memory.id in processed:
                    continue
                
                # Merge memories
                merged_content = await llm_service.merge_memories(
                    memory.content,
                    similar_memory.content
                )
                
                # Update main memory
                memory.content = merged_content
                await self.db.commit()
                
                # Archive duplicate
                await self.memory_service.archive_memory(
                    similar_memory.id,
                    "merged"
                )
                
                processed.add(similar_memory.id)
                merged_count += 1
        
        print(f"Merged {merged_count} duplicate memories in {namespace}")
        return merged_count


from datetime import datetime
