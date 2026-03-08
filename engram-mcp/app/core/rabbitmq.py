import aio_pika
import json
from typing import Optional, Callable, Any
from app.core.config import get_settings

settings = get_settings()


class RabbitMQClient:
    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        
        # Queue names
        self.QUEUE_MEMORY_STORE = "engram.memory.store"
        self.QUEUE_MEMORY_CLASSIFY = "engram.memory.classify"
        self.QUEUE_MEMORY_DECAY = "engram.memory.decay"
        self.QUEUE_MEMORY_CLEANUP = "engram.memory.cleanup"
        self.QUEUE_MEMORY_MERGE = "engram.memory.merge"
        self.QUEUE_TRIGGER_PROCESS = "engram.trigger.process"
        self.QUEUE_TOPIC_REBUILD = "engram.topic.rebuild"
    
    async def connect(self):
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        
        # Declare queues
        for queue_name in [
            self.QUEUE_MEMORY_STORE,
            self.QUEUE_MEMORY_CLASSIFY,
            self.QUEUE_MEMORY_DECAY,
            self.QUEUE_MEMORY_CLEANUP,
            self.QUEUE_MEMORY_MERGE,
            self.QUEUE_TRIGGER_PROCESS,
            self.QUEUE_TOPIC_REBUILD,
        ]:
            await self.channel.declare_queue(queue_name, durable=True)
    
    async def close(self):
        if self.connection:
            await self.connection.close()
    
    async def publish(self, queue: str, message: dict):
        """Publish message to queue"""
        if not self.channel:
            await self.connect()
        
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue,
        )
    
    async def consume(self, queue: str, handler: Callable):
        """Consume messages from queue"""
        if not self.channel:
            await self.connect()
        
        queue_obj = await self.channel.declare_queue(queue, durable=True)
        
        async with queue_obj.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        await handler(data)
                    except Exception as e:
                        print(f"Error processing message: {e}")
    
    # Convenience methods for publishing
    async def queue_store(self, namespace: str, memory_id: str, content: str, context: dict, tags: list):
        await self.publish(self.QUEUE_MEMORY_STORE, {
            "action": "store",
            "namespace": namespace,
            "memory_id": memory_id,
            "content": content,
            "context": context,
            "tags": tags,
        })
    
    async def queue_classify(self, namespace: str, memory_id: str, content: str):
        await self.publish(self.QUEUE_MEMORY_CLASSIFY, {
            "action": "classify",
            "namespace": namespace,
            "memory_id": memory_id,
            "content": content,
        })
    
    async def queue_decay(self, namespace: str, layer: str):
        await self.publish(self.QUEUE_MEMORY_DECAY, {
            "action": "decay",
            "namespace": namespace,
            "layer": layer,
        })
    
    async def queue_cleanup(self, namespace: str):
        await self.publish(self.QUEUE_MEMORY_CLEANUP, {
            "action": "cleanup",
            "namespace": namespace,
        })
    
    async def queue_merge(self, namespace: str, memory_id1: str, memory_id2: str):
        await self.publish(self.QUEUE_MEMORY_MERGE, {
            "action": "merge",
            "namespace": namespace,
            "memory_id1": memory_id1,
            "memory_id2": memory_id2,
        })
    
    async def queue_trigger(self, namespace: str, trigger_tag: str, context: dict):
        await self.publish(self.QUEUE_TRIGGER_PROCESS, {
            "action": "trigger",
            "namespace": namespace,
            "trigger_tag": trigger_tag,
            "context": context,
        })
    
    async def queue_topic_rebuild(self, namespace: str, topic_id: str = None):
        await self.publish(self.QUEUE_TOPIC_REBUILD, {
            "action": "rebuild",
            "namespace": namespace,
            "topic_id": topic_id,
        })


rabbitmq_client = RabbitMQClient()


async def get_rabbitmq():
    return rabbitmq_client
