from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.db import get_db, get_redis

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    redis_client = await get_redis()
    
    db_status = "healthy"
    redis_status = "healthy"
    
    try:
        await db.execute("SELECT 1")
    except Exception:
        db_status = "unhealthy"
    
    try:
        await redis_client.ping()
    except Exception:
        redis_status = "unhealthy"
    
    return HealthResponse(
        status="healthy",
        database=db_status,
        redis=redis_status
    )


@router.get("/services")
async def services_status():
    return {
        "services": {
            "postgres": "localhost:5432",
            "redis": "localhost:6379",
            "rabbitmq": "localhost:5672",
            "qdrant": "localhost:6333",
            "clickhouse": "localhost:8123",
            "minio": "localhost:9000",
            "langfuse": "localhost:3000",
            "litellm": "localhost:4000"
        }
    }
