from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, Boolean, JSON, Index, ForeignKey
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.types import TypeDecorator, LargeBinary
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import json
import numpy as np


class Vector(TypeDecorator):
    """PostgreSQL vector type for pgvector"""
    impl = LargeBinary
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, np.ndarray)):
            value = np.array(value, dtype=np.float32)
            return value.tobytes()
        return value
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return np.frombuffer(value, dtype=np.float32).tolist()
    
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(LargeBinary())


class Base(DeclarativeBase):
    pass


class Memory(Base):
    __tablename__ = "memories"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(64), nullable=False, default="default", index=True)
    content = Column(Text, nullable=False)
    context = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    
    # Classification
    memory_type = Column(String(32), default="semantic", index=True)  # episodic, semantic, procedural
    
    # Layer management
    layer = Column(String(16), default="buffer", index=True)  # buffer, working, core
    activation_score = Column(Float, default=1.0)
    decay_score = Column(Float, default=1.0)
    
    # Important memory flag - core memories that should never be deleted
    is_important = Column(Boolean, default=False, index=True)
    importance_reason = Column(Text, nullable=True)  # Why this is marked as important
    importance_score = Column(Float, default=0.0)  # 0-1, higher = more important
    
    # Auto-protected: system-marked important memories
    is_auto_protected = Column(Boolean, default=False)
    protection_source = Column(String(64), nullable=True)  # 'llm', 'user', 'system', 'frequent_access'
    
    # Vector embedding (1536 dims for text-embedding-3-small)
    embedding = Column(Vector)
    
    # Topic clustering
    topic_id = Column(String(36), ForeignKey("topics.id"), nullable=True, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    accessed_at = Column(DateTime, default=func.now())
    access_count = Column(Integer, default=0)
    
    # Source tracking
    source_type = Column(String(32), default="manual")  # api, webhook, file, agent
    source_id = Column(String(64), nullable=True)
    
    # Quality scores (LLM-evaluated)
    quality_score = Column(Float, nullable=True)
    importance_score = Column(Float, nullable=True)
    
    # Soft delete
    is_deleted = Column(Boolean, default=False)
    
    __table_args__ = (
        Index("idx_memories_namespace_layer", "namespace", "layer"),
        Index("idx_memories_namespace_type", "namespace", "memory_type"),
        Index("idx_memories_namespace_topic", "namespace", "topic_id"),
        Index("idx_memories_decay_score", "namespace", "decay_score"),
    )


class Topic(Base):
    __tablename__ = "topics"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(64), nullable=False, default="default", index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    
    # Parent topic for hierarchy
    parent_id = Column(String(36), ForeignKey("topics.id"), nullable=True, index=True)
    
    # Cluster stats
    memory_count = Column(Integer, default=0)
    avg_quality = Column(Float, nullable=True)
    
    # LLM-generated summary
    summary = Column(Text, nullable=True)
    keywords = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_topics_namespace_parent", "namespace", "parent_id"),
    )


class ArchivedMemory(Base):
    __tablename__ = "archived_memories"
    
    id = Column(String(36), primary_key=True)
    original_id = Column(String(36), nullable=False, index=True)
    namespace = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=False)
    context = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    memory_type = Column(String(32))
    layer = Column(String(16))
    reason = Column(String(64), nullable=False)  # decay_below_threshold, merged, manual
    archived_at = Column(DateTime, default=func.now())


class TriggerRule(Base):
    __tablename__ = "trigger_rules"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(64), nullable=False, default="default", index=True)
    name = Column(String(256), nullable=False)
    trigger_tag = Column(String(128), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Query configuration
    query_text = Column(Text, nullable=True)
    memory_types = Column(JSON, default=list)  # episodic, semantic, procedural
    layers = Column(JSON, default=list)  # buffer, working, core
    limit = Column(Integer, default=10)
    
    # Filters
    min_importance = Column(Float, nullable=True)  # Minimum importance score
    min_quality = Column(Float, nullable=True)  # Minimum quality score
    is_important_only = Column(Boolean, default=False)  # Only important memories
    
    # Action configuration
    action_type = Column(String(32), default="recall")  # recall, search, summarize, promote
    response_format = Column(String(32), default="default")
    
    # Priority (higher = more important)
    priority = Column(Integer, default=0)
    
    # Conditions
    conditions = Column(JSON, nullable=True)  # Custom conditions
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AccessLog(Base):
    __tablename__ = "access_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(64), nullable=False, index=True)
    memory_id = Column(String(36), nullable=False, index=True)
    access_type = Column(String(32), nullable=False)  # recall, search, browse
    query = Column(Text, nullable=True)
    result_count = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    accessed_at = Column(DateTime, default=func.now())


# Database engine setup
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
