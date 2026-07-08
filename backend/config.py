import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    supabase_url: str = Field(default="", alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    allowed_origins: str = "http://localhost:3000"
    max_file_size_mb: int = 10
    model: str = Field(default="meta/llama-3.1-8b-instruct", alias="MODEL")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', '.env'),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

settings = Settings()

