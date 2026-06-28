from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    nvidia_api_key: str = ""
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_service_key: str = ""
    allowed_origins: str = "http://localhost:3000"
    max_file_size_mb: int = 10

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
