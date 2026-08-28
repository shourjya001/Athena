from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = "sqlite:///~/.trackboard/app.db"
    tz: str = "Asia/Kolkata"
    app_tz: str = ""
    scheduler_mode: str = "local"

    session_secret: str = "change-me"
    allowed_emails: str = ""
    owner_email: str = ""
    dev_user_email: str = "you@example.com"
    contact_email: str = "you@example.com"

    youtube_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    llm_redact_pii: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "shourjya.h@gmail.com"

    @property
    def db_path(self) -> Path:
        if os.getenv("VERCEL") and not os.getenv("DB_URL"):
            return Path("/tmp/app.db")
        raw = self.db_url
        if raw.startswith("sqlite:///"):
            raw = raw[len("sqlite:///") :]
        return Path(os.path.expanduser(raw)).resolve()

    @property
    def allowlist(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    @property
    def user_agent(self) -> str:
        return f"Trackboard/0.1 (+{self.contact_email})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
