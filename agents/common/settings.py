"""Typed configuration loader.

All environment variables the system understands are defined here. Runtime
code never reads ``os.environ`` directly — that keeps the surface area of
configuration testable and documented.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration.

    Values are read from environment (or a ``.env`` file in dev). Every field
    has a sensible default so that ``Settings()`` in tests does not explode.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Runtime ---
    env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- Postgres ---
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://swarmscout:swarmscout@localhost:5432/swarmscout"
    )

    # --- DGrid ---
    dgrid_base_url: str = Field(default="https://api.dgrid.ai/v1")
    dgrid_api_key: str = Field(default="")

    # --- Direct providers ---
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")

    # --- Per-agent primaries ---
    hunter_primary_model: str = Field(default="google/gemini-2.5-flash")
    social_primary_model: str = Field(default="openai/gpt-4o")
    chain_primary_model: str = Field(default="anthropic/claude-sonnet-4-6")
    risk_primary_model: str = Field(default="anthropic/claude-opus-4-7")
    narrator_primary_model: str = Field(default="anthropic/claude-opus-4-7")

    # --- Four.meme ---
    fourmeme_source: str = Field(default="polling")
    fourmeme_poll_url: str = Field(default="https://four.meme/api/tokens/new")
    fourmeme_poll_interval_seconds: int = Field(default=10, ge=1)

    # --- Chain ---
    bnb_testnet_rpc_url: str = Field(default="https://bsc-testnet-rpc.publicnode.com")
    bnb_chain_id: int = Field(default=97)
    findings_registry_address: str = Field(default="0x0000000000000000000000000000000000000000")
    agent_wallet_private_key: str = Field(default="")
    bscscan_api_key: str = Field(default="")
    bscscan_base_url: str = Field(default="https://api-testnet.bscscan.com/api")

    # --- Telegram ---
    telegram_bot_token: str = Field(default="")

    # --- Playwright ---
    playwright_headless: bool = Field(default=True)
    playwright_user_data_dir: str = Field(default="/tmp/swarmscout-pw")  # noqa: S108

    # --- Cost caps ---
    daily_cost_cap_usd_anthropic: float = Field(default=50)
    daily_cost_cap_usd_openai: float = Field(default=50)
    daily_cost_cap_usd_google: float = Field(default=20)
    daily_cost_cap_usd_dgrid: float = Field(default=100)

    # --- Rates ---
    api_rate_limit_per_minute: int = Field(default=60)
    bscscan_rate_limit_per_sec: int = Field(default=4)

    # --- URLs ---
    public_api_url: str = Field(default="http://localhost:8000")
    public_dashboard_url: str = Field(default="http://localhost:3000")
    ws_path: str = Field(default="/ws/events")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton ``Settings`` instance for this process."""
    return Settings()
