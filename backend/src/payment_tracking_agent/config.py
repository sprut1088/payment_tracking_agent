"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the backend/ directory, regardless of where the server is launched from.
_BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PTA_",
        env_file=str(_BACKEND_ROOT / ".env"),  # absolute path — works regardless of CWD
        env_file_encoding="utf-8",  # explicit — avoids cp1252/utf-8 mismatch across platforms
        extra="ignore",
    )

    app_name: str = "ACH Payment Tracking Agent"
    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Directory where raw uploaded CCD files are saved (created on first upload)
    upload_dir: str = "uploaded_files/ccd"

    # ---------------------------------------------------------------------------
    # Persistence — JSON snapshot of the in-memory ledger
    # Set persist_interval_seconds > 0 to enable periodic disk flush.
    # Set to 0 to disable auto-persistence (data lost on restart).
    # ---------------------------------------------------------------------------
    data_dir: str = str(_BACKEND_ROOT / "database_json")
    persist_interval_seconds: int = 30  # flush dirty store every 30 s

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
    # Drop folder watched by the scheduler (frontend buttons use demo-inbox/returns)
    return_scan_dir: str = str(_BACKEND_ROOT / "drop" / "returns" / "input")
    return_scan_processed_dir: str = str(_BACKEND_ROOT / "drop" / "returns" / "processed")
    return_scan_error_dir: str = str(_BACKEND_ROOT / "drop" / "returns" / "error")

    # Scheme directory (simulates onward submission to the ACH scheme)
    scheme_dir: str = "uploaded_files/scheme"

    # Scheduler intervals (seconds)
    return_scan_interval_seconds: int = 30
    scheme_push_interval_seconds: int = 5
    # Auto-simulation disabled by default — payments only advance to WITH BENEFICIARY BANK
    # when an actual settlement file is received (via Check Settlement or drop/settlement/input/).
    # Set to a positive value to re-enable the auto-simulator.
    settlement_simulation_interval_seconds: int = 0

    # Settlement rejection file directories
    settlement_dir: str = "uploaded_files/settlement"   # where API-uploaded files are saved
    # Drop folder watched by the scheduler (frontend buttons use demo-inbox/settlement)
    settlement_scan_dir: str = str(_BACKEND_ROOT / "drop" / "settlement" / "input")
    settlement_scan_processed_dir: str = str(_BACKEND_ROOT / "drop" / "settlement" / "processed")
    settlement_scan_error_dir: str = str(_BACKEND_ROOT / "drop" / "settlement" / "error")
    settlement_scan_interval_seconds: int = 30

    # CCD drop folder watched by the scheduler (frontend buttons use demo-inbox/ccd)
    ccd_scan_dir: str = str(_BACKEND_ROOT / "drop" / "ccd" / "input")
    ccd_scan_processed_dir: str = str(_BACKEND_ROOT / "drop" / "ccd" / "processed")
    ccd_scan_under_review_dir: str = str(_BACKEND_ROOT / "drop" / "ccd" / "under-review")
    ccd_scan_error_dir: str = str(_BACKEND_ROOT / "drop" / "ccd" / "error")
    ccd_scan_interval_seconds: int = 15

    # Local-folder demo flow (Prompt 04).
    # Required folder layout under demo_flow_root:
    # ccd, settlement, scheme-reject, returns, processed.
    # A user drops a CCD file into <demo_flow_root>/<inbox_subdir>. That drop
    # becomes T0 for the batch. Later scans look for related settlement and
    # scheme-reject files at T0 + settlement_delay_seconds, and NACHA return
    # files at T0 + returns_delay_seconds.
    demo_flow_root: Path = _BACKEND_ROOT / "demo-inbox"
    inbox_subdir: str = "ccd"
    settlement_subdir: str = "settlement"
    scheme_reject_subdir: str = "scheme-reject"
    returns_subdir: str = "returns"
    processed_subdir: str = "processed"
    under_review_subdir: str = "under-review"
    settlement_delay_seconds: int = 120
    returns_delay_seconds: int = 240
    poll_interval_seconds: int = 5


settings = Settings()
