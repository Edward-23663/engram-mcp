from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class MemoryCreate(BaseModel):
    content: str
    context: Optional[Dict[str, Any]] = {}
    tags: Optional[List[str]] = []
    memory_type: Optional[str] = "semantic"
    source_type: Optional[str] = "manual"
    source_id: Optional[str] = None
    trigger_tag: Optional[str] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    memory_type: Optional[str] = None


class MemoryResponse(BaseModel):
    id: str
    namespace: str
    content: str
    context: Dict[str, Any]
    tags: List[str]
    memory_type: str
    layer: str
    activation_score: float
    decay_score: float
    is_important: bool
    importance_reason: Optional[str]
    importance_score: Optional[float]
    is_auto_protected: bool
    protection_source: Optional[str]
    topic_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    accessed_at: datetime
    access_count: int
    source_type: str
    source_id: Optional[str]
    quality_score: Optional[float]

    class Config:
        from_attributes = True


class MemorySearchRequest(BaseModel):
    query: str
    namespace: Optional[str] = "default"
    memory_types: Optional[List[str]] = []
    layers: Optional[List[str]] = []
    topic_id: Optional[str] = None
    limit: Optional[int] = 10
    include_scores: Optional[bool] = True
    min_importance: Optional[float] = None
    min_quality: Optional[float] = None
    is_important_only: Optional[bool] = False


class MemorySearchResponse(BaseModel):
    results: List[MemoryResponse]
    scores: List[float]
    total: int
    query_time_ms: int


class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None


class TopicResponse(BaseModel):
    id: str
    namespace: str
    name: str
    description: Optional[str]
    parent_id: Optional[str]
    memory_count: int
    avg_quality: Optional[float]
    summary: Optional[str]
    keywords: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TriggerRuleCreate(BaseModel):
    name: str
    trigger_tag: str
    description: Optional[str] = None
    query_text: Optional[str] = None
    memory_types: Optional[List[str]] = []
    layers: Optional[List[str]] = []
    limit: Optional[int] = 10
    min_importance: Optional[float] = None
    min_quality: Optional[float] = None
    is_important_only: Optional[bool] = False
    action_type: Optional[str] = "recall"
    response_format: Optional[str] = "default"
    priority: Optional[int] = 0
    conditions: Optional[Dict[str, Any]] = None


class TriggerRuleResponse(BaseModel):
    id: str
    namespace: str
    name: str
    trigger_tag: str
    description: Optional[str]
    query_text: Optional[str]
    memory_types: List[str]
    layers: List[str]
    limit: int
    min_importance: Optional[float]
    min_quality: Optional[float]
    is_important_only: bool
    action_type: str
    response_format: str
    priority: int
    conditions: Optional[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResumeResponse(BaseModel):
    core: List[MemoryResponse]
    recent: List[MemoryResponse]
    topics: List[TopicResponse]
    triggers: List[TriggerRuleResponse]


class StatsResponse(BaseModel):
    total_memories: int
    by_layer: Dict[str, int]
    by_type: Dict[str, int]
    topics_count: int
    archived_count: int
