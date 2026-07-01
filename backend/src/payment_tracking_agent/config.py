"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PTA_", env_file=".env", extra="ignore")

    app_name: str = "ACH Payment Tracking Agent"
    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
