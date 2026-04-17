"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "contract-risk-analyzer"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, gt=0)

    azure_search_endpoint: str | None = None
    azure_search_api_key: str | None = None
    azure_search_index_name: str = "contract-kb"

    database_url: str = "sqlite:///./data/app.db"
    mailgun_webhook_secret: str | None = None

    upload_dir: Path = Field(default=Path("./data/uploads"))
    model_config_dir: Path = Field(default=Path("./config/models"))
    prompt_dir: Path = Field(default=Path("./app/infra/llm/prompts"))

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize logging level names for the standard logging module."""
        return value.upper()

    @model_validator(mode="after")
    def validate_paths(self) -> "Settings":
        """Validate required local config directories and create upload storage."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if not self.model_config_dir.exists():
            raise ValueError(f"Model config directory does not exist: {self.model_config_dir}")
        if not self.prompt_dir.exists():
            raise ValueError(f"Prompt directory does not exist: {self.prompt_dir}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for application runtime."""
    return Settings()
