from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "AI SQL Assistant"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    database_url: str = ""
    mssql_url: str = ""
    postgres_url: str = ""
    mysql_url: str = ""
    mongodb_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    llm_provider: str = "mistral"
    query_timeout_seconds: int = 30
    max_result_rows: int = 200
    schema_cache_seconds: int = 300

    # Resolve dotenv files from the source tree instead of the process working
    # directory.  The documented command runs uvicorn from the project root,
    # while the documented dotenv file lives in backend/.env.
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
