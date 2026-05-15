"""Application settings loaded from environment variables.

Uses pydantic-settings so every config value is typed and validated at boot.
WhatsApp credentials are optional — they're only required if you wire up
the Meta webhook. The web demo (HTML + /chat endpoint) runs without them.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # WhatsApp Cloud API — optional; only required for the /webhook routes.
    whatsapp_token: str | None = Field(default=None, alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str | None = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str | None = Field(default=None, alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str | None = Field(default=None, alias="WHATSAPP_APP_SECRET")

    model_id: str = Field(default="claude-opus-4-7", alias="MODEL_ID")
    max_history_messages: int = Field(default=20, alias="MAX_HISTORY_MESSAGES")


settings = Settings()  # type: ignore[call-arg]


def whatsapp_configured() -> bool:
    """True when all WhatsApp creds are set — webhook routes need this."""
    return all(
        bool(getattr(settings, name))
        for name in (
            "whatsapp_token",
            "whatsapp_phone_number_id",
            "whatsapp_verify_token",
            "whatsapp_app_secret",
        )
    )
