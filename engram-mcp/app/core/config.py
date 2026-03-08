from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://app:postgres_password@localhost:5432/appdb"
    
    # Redis
    REDIS_URL: str = "redis://:redis_password@localhost:6379/0"
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    
    # LiteLLM
    LITELLM_BASE_URL: str = "http://localhost:4000"
    LITELLM_API_KEY: str = "litellm_key_123"
    LITELLM_EMBED_MODEL: str = "text-embedding-3-small"
    LITELLM_CHAT_MODEL: str = "gpt-4o-mini"
    
    # Application
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    NAMESPACE: str = "default"
    
    # Memory settings
    BUFFER_MAX_SIZE: int = 1000
    WORKING_MAX_SIZE: int = 500
    DECAY_THRESHOLD: float = 0.01
    SIMILARITY_THRESHOLD: float = 0.78
    
    # Memory decay half-lives (in seconds)
    EPISODIC_HALF_LIFE: int = 86400 * 7      # 7 days
    SEMANTIC_HALF_LIFE: int = 86400 * 30     # 30 days
    PROCEDURAL_HALF_LIFE: int = 86400 * 90   # 90 days
    
    # Topic settings
    TOPIC_CLUSTER_THRESHOLD: int = 10
    
    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
