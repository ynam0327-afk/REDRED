from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str  # postgresql+asyncpg://... 형태지만 asyncpg 직접 사용 시 postgresql://로 변환해서 씀
    redis_url: str = "redis://redis:6379/0"
    redis_stream_key: str = "fire_events_stream"
    consumer_group: str = "ingest-worker-group"
    consumer_name: str = "ingest-worker-1"

    class Config:
        env_file = ".env"


settings = Settings()
