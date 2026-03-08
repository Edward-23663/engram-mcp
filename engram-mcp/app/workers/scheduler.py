"""
Background task scheduler using RabbitMQ for async task execution
"""
import asyncio
import logging
from datetime import datetime, timedelta
from app.core.rabbitmq import rabbitmq_client
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


class TaskScheduler:
    """Background task scheduler for memory management"""
    
    def __init__(self):
        self.running = False
        self.tasks = []
    
    async def start(self):
        """Start the scheduler"""
        await rabbitmq_client.connect()
        self.running = True
        
        logger.info("Task scheduler started")
        
        asyncio.create_task(self.schedule_decay())
        asyncio.create_task(self.schedule_cleanup())
        asyncio.create_task(self.schedule_merge())
        asyncio.create_task(self.schedule_promotion())
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        await rabbitmq_client.close()
        logger.info("Task scheduler stopped")
    
    async def schedule_decay(self):
        """Schedule memory decay tasks every hour"""
        while self.running:
            try:
                namespaces = settings.NAMESPACE.split(",")
                for ns in namespaces:
                    ns = ns.strip()
                    for layer in ["buffer", "working"]:
                        await rabbitmq_client.queue_decay(ns, layer)
                        logger.info(f"Queued decay task for {ns}/{layer}")
            except Exception as e:
                logger.error(f"Error in decay scheduler: {e}")
            
            await asyncio.sleep(3600)  # Run every hour
    
    async def schedule_cleanup(self):
        """Schedule memory cleanup tasks every 6 hours"""
        while self.running:
            try:
                namespaces = settings.NAMESPACE.split(",")
                for ns in namespaces:
                    ns = ns.strip()
                    await rabbitmq_client.queue_cleanup(ns)
                    logger.info(f"Queued cleanup task for {ns}")
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")
            
            await asyncio.sleep(21600)  # Run every 6 hours
    
    async def schedule_merge(self):
        """Schedule memory merge/dedup tasks every 12 hours"""
        while self.running:
            try:
                namespaces = settings.NAMESPACE.split(",")
                for ns in namespaces:
                    ns = ns.strip()
                    await rabbitmq_client.publish("engram.memory.merge", {
                        "action": "merge",
                        "namespace": ns,
                    })
                    logger.info(f"Queued merge task for {ns}")
            except Exception as e:
                logger.error(f"Error in merge scheduler: {e}")
            
            await asyncio.sleep(43200)  # Run every 12 hours
    
    async def schedule_promotion(self):
        """Schedule memory promotion tasks every 2 hours"""
        while self.running:
            try:
                namespaces = settings.NAMESPACE.split(",")
                for ns in namespaces:
                    ns = ns.strip()
                    await rabbitmq_client.publish("engram.memory.promotion", {
                        "action": "promote",
                        "namespace": ns,
                    })
                    logger.info(f"Queued promotion task for {ns}")
            except Exception as e:
                logger.error(f"Error in promotion scheduler: {e}")
            
            await asyncio.sleep(7200)  # Run every 2 hours


async def run_scheduler():
    """Run the scheduler as a standalone service"""
    scheduler = TaskScheduler()
    await scheduler.start()
    
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(run_scheduler())
