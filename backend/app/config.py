"""Application settings loaded from environment variables (and `.env` in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"

    database_url: str = "sqlite:///./researchpilot.db"
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    key_encryption_secret: str = ""

    # Comma-separated list, e.g. "http://localhost:5173,https://researchpilot.vercel.app"
    cors_allowed_origins: str = "http://localhost:5173"

    openalex_mailto: str = ""
    semantic_scholar_api_key: str = ""

    # Development-only fallback LLM keys; production uses per-user (BYOK) keys.
    dev_groq_api_key: str = Field(default="", repr=False)
    dev_gemini_api_key: str = Field(default="", repr=False)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
