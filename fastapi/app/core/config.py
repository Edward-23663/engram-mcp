from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app:postgres_password@postgres:5432/appdb"
    redis_url: str = "redis://:redis_password@redis:6379"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672"
    litellm_base_url: str = "http://litellm:4000"
    litellm_api_key: str = "litellm_key_123"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://langfuse-web:3000"

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
