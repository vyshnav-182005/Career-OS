import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

_backend_env = os.path.join(os.path.dirname(__file__), '.env')
_frontend_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', '.env')

class Settings(BaseSettings):
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    adzuna_app_id: str = Field(default="", alias="ADZUNA_APP_ID")
    adzuna_app_key: str = Field(default="", alias="ADZUNA_APP_KEY")
    job_api_key_2: str = Field(default="", alias="JOOBLE_API_KEY")
    # Comma-separated provider names; see services/job_providers/registry.py
    job_providers: str = Field(default="jooble,greenhouse,lever", alias="JOB_PROVIDERS")
    internal_api_secret: str = Field(default="", alias="INTERNAL_API_SECRET")
    allowed_origins: str = "http://localhost:3000"
    max_file_size_mb: int = 10
    # NVIDIA retired the llama-3.1 family (410 Gone, 2026-08-26). This is the
    # general-purpose model for every agent; see services/llm_client.py for why
    # each call site must pass NO_THINKING with it.
    model: str = Field(default="nvidia/nemotron-3-super-120b-a12b", alias="MODEL")

    model_config = SettingsConfigDict(
        # backend/.env takes priority; frontend/.env is fallback
        env_file=(_backend_env, _frontend_env),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

settings = Settings()

