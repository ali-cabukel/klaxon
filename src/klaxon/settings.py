"""Env-driven settings for the incident desk, Slack layer, and agent."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "klaxon.db"

DEFAULT_BOT_SCOPES = (
    "app_mentions:read,channels:history,chat:write,commands,"
    "im:history,im:write,reactions:write,users:read"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DB}"

    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""
    slack_bot_scopes: str = DEFAULT_BOT_SCOPES
    slack_user_scopes: str = ""

    public_base_url: str = "http://localhost:3000"
    state_secret: str = "dev-only"
    token_encryption_key: str = ""

    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-4-20250514"
    conversation_ttl_seconds: int = 1800
    mcp_url: str = ""

    @field_validator("public_base_url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def bot_scopes(self) -> list[str]:
        return [s.strip() for s in self.slack_bot_scopes.split(",") if s.strip()]

    @property
    def user_scopes(self) -> list[str]:
        return [s.strip() for s in self.slack_user_scopes.split(",") if s.strip()]

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/slack/oauth/callback"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> str:
        url = self.database_url
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url.startswith(prefix):
                return url[len(prefix) :]
        return url

    @property
    def agent_enabled(self) -> bool:
        return bool(self.anthropic_api_key and self.agent_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
