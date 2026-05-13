"""Application settings loaded from environment variables.

Uses pydantic-settings so every config value is typed and validated at boot.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    whatsapp_token: str = Field(..., alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str = Field(..., alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str = Field(..., alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str = Field(..., alias="WHATSAPP_APP_SECRET")

    model_id: str = Field(default="claude-opus-4-7", alias="MODEL_ID")
    max_history_messages: int = Field(default=20, alias="MAX_HISTORY_MESSAGES")


settings = Settings()  # type: ignore[call-arg]
