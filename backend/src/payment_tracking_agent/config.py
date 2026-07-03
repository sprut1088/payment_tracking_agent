"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PTA_", env_file=".env", extra="ignore")

    app_name: str = "ACH Payment Tracking Agent"
    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Local-folder demo flow (Prompt 04).
    # Required folder layout under demo_flow_root:
    # ccd, settlement, scheme-reject, returns, processed.
    # A user drops a CCD file into <demo_flow_root>/<inbox_subdir>. That drop
    # becomes T0 for the batch. Later scans look for related settlement and
    # scheme-reject files at T0 + settlement_delay_seconds, and NACHA return
    # files at T0 + returns_delay_seconds.
    demo_flow_root: Path = Path("demo-inbox")
    inbox_subdir: str = "ccd"
    settlement_subdir: str = "settlement"
    scheme_reject_subdir: str = "scheme-reject"
    returns_subdir: str = "returns"
    processed_subdir: str = "processed"
    settlement_delay_seconds: int = 120
    returns_delay_seconds: int = 240
    poll_interval_seconds: int = 5


settings = Settings()
