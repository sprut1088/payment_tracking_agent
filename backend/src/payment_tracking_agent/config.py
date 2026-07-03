"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PTA_", env_file=".env", extra="ignore")

    app_name: str = "ACH Payment Tracking Agent"
    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Directory where raw uploaded CCD files are saved (created on first upload)
    upload_dir: str = "uploaded_files/ccd"

    # ---------------------------------------------------------------------------
    # LLM settings
    # Supports both PTA_-prefixed names (project standard) and the common bare
    # names used by most AI project .env files (LLM_PROVIDER, ANTHROPIC_API_KEY…)
    # ---------------------------------------------------------------------------
    llm_api_key: str | None = None  # PTA_LLM_API_KEY  (OpenAI / OpenRouter key)

    # ANTHROPIC_API_KEY is read without the PTA_ prefix (standard Anthropic convention)
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "PTA_ANTHROPIC_API_KEY"),
    )

    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("PTA_LLM_PROVIDER", "LLM_PROVIDER"),
    )  # "openai" | "anthropic"

    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("PTA_LLM_MODEL", "LLM_MODEL"),
    )  # e.g. claude-3-5-haiku-20241022  or  gpt-4o-mini

    llm_max_tokens: int = Field(
        default=2000,
        validation_alias=AliasChoices("PTA_LLM_MAX_TOKENS", "LLM_MAX_TOKENS"),
    )

    llm_base_url: str | None = None  # Override for Azure OpenAI or custom endpoints

    # Return file directories
    return_dir: str = "uploaded_files/returns"       # where API-uploaded return files are saved
    return_scan_dir: str = "drop/returns"            # folder polled by the scheduler

    # Scheme directory (simulates onward submission to the ACH scheme)
    scheme_dir: str = "uploaded_files/scheme"

    # Scheduler intervals (seconds)
    return_scan_interval_seconds: int = 30
    scheme_push_interval_seconds: int = 30

    # Settlement rejection file directories
    settlement_dir: str = "uploaded_files/settlement"   # where API-uploaded files are saved
    settlement_scan_dir: str = "drop/settlement"         # folder polled by the scheduler
    settlement_scan_interval_seconds: int = 30


settings = Settings()
