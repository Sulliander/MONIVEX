from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONIVEX_")
    database_url: str = "sqlite:////data/monivex.db"
    setup_token: str = Field(default="", repr=False)
    public_origin: str = "http://localhost:8080"
    cookie_secure: bool = True
    allowed_networks: str = ""
    encryption_key: str = Field(default="", repr=False)
    worker_concurrency: int = Field(default=10, ge=1, le=100)
    worker_lease_seconds: int = Field(default=30, ge=15, le=300)
    manual_concurrency: int = Field(default=2, ge=1, le=10)
    session_hours: int = Field(default=12, ge=1, le=168)


@lru_cache
def get_settings() -> Settings:
    return Settings()
