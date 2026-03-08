import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()


class RedisClient:
    def __init__(self):
        self.client: redis.Redis = None
    
    async def connect(self):
        self.client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        await self.client.ping()
    
    async def close(self):
        if self.client:
            await self.client.close()
    
    # Cache operations
    async def cache_memory(self, memory_id: str, data: dict, ttl: int = 3600):
        key = f"memory:{memory_id}"
        await self.client.setex(key, ttl, str(data))
    
    async def get_cached_memory(self, memory_id: str) -> dict:
        key = f"memory:{memory_id}"
        data = await self.client.get(key)
        return eval(data) if data else None
    
    async def delete_cached_memory(self, memory_id: str):
        key = f"memory:{memory_id}"
        await self.client.delete(key)
    
    # Activation tracking
    async def increment_activation(self, memory_id: str) -> int:
        key = f"activation:{memory_id}"
        count = await self.client.incr(key)
        await self.client.expire(key, 86400 * 7)  # 7 days
        return count
    
    async def get_activation(self, memory_id: str) -> int:
        key = f"activation:{memory_id}"
        count = await self.client.get(key)
        return int(count) if count else 0
    
    # Buffer/Working layer caching
    async def cache_layer_memories(self, namespace: str, layer: str, memory_ids: list):
        key = f"layer:{namespace}:{layer}"
        await self.client.delete(key)
        if memory_ids:
            await self.client.sadd(key, *memory_ids)
            await self.client.expire(key, 300)  # 5 minutes
    
    async def get_layer_memories(self, namespace: str, layer: str) -> list:
        key = f"layer:{namespace}:{layer}"
        return list(await self.client.smembers(key))
    
    # Topic cache
    async def cache_topics(self, namespace: str, topics: list):
        key = f"topics:{namespace}"
        await self.client.delete(key)
        if topics:
            await self.client.sadd(key, *topics)
            await self.client.expire(key, 300)
    
    async def get_cached_topics(self, namespace: str) -> list:
        key = f"topics:{namespace}"
        return list(await self.client.smembers(key))
    
    # Decay task queue
    async def queue_decay_task(self, namespace: str, layer: str):
        key = "decay:queue"
        await self.client.sadd(key, f"{namespace}:{layer}")
        await self.client.expire(key, 86400)
    
    async def get_decay_queue(self) -> list:
        key = "decay:queue"
        return list(await self.client.smembers(key))
    
    async def clear_decay_task(self, namespace: str, layer: str):
        key = "decay:queue"
        await self.client.srem(key, f"{namespace}:{layer}")


redis_client = RedisClient()


async def get_redis():
    return redis_client
