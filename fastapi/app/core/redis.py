import redis.asyncio as redis
from app.core.config import settings

redis_client = None


async def init_redis():
    global redis_client
    redis_client = await redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )
    return redis_client


async def get_redis():
    return redis_client
