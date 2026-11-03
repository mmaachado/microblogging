from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./microblogging.sqlite3"
    allowed_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = True
    session_ttl_days: int = 30
    registration_rate_per_minute: int = 30
    password_hash_concurrency: int = 4
    image_processing_concurrency: int = 2
    media_dir: str = "media"
    max_request_bytes: int = 65536
    log_file: str = "logs/backend.log"
    log_level: str = "INFO"
    cache_url: str | None = None
    broker_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
