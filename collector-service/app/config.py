from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bigdata119_api_key: str
    safetydata_api_key: str
    redis_url: str = "redis://redis:6379/0"
    redis_stream_key: str = "fire_events_stream"
    poll_interval_seconds: int = 3600

    class Config:
        env_file = ".env"


settings = Settings()
