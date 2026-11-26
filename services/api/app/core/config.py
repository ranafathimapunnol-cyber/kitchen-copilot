from pathlib import Path

from pydantic import SecretStr  # type: ignore
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    APP_NAME: str = "Kitchen Copilot API"
    APP_VERSION: str = "0.1.0"
    AGENT_ENABLED: bool = False

    # Private storage for supplier bill attachments (ADR-008). "local" keeps
    # files on disk, outside the repository, for development. The production
    # S3-compatible provider is not chosen yet (decision D9).
    ATTACHMENT_STORAGE_BACKEND: str = "local"
    ATTACHMENT_STORAGE_DIR: str = str(
        Path.home() / "kitchen-copilot-data" / "bill-attachments"
    )

    # The campuses' local time zone. Business dates ("today", "this
    # month", "a payment cannot be dated in the future") follow it, not the
    # server clock, which is UTC in the Docker image.
    APP_TIMEZONE: str = "Asia/Kolkata"

    # Gemini AI configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    # Stage 12: the external model is used only when AGENT_ENABLED is true
    # and a key is configured; it only helps read the request (never sees
    # tool results). Approved procedure documents (Markdown) for retrieval.
    AGENT_LLM_TIMEOUT_SECONDS: float = 12.0
    AGENT_PROCEDURES_DIR: str | None = None
    AGENT_PROPOSAL_TTL_HOURS: int = 72

    DATABASE_URL: str
    SECRET_KEY: str

    # JWT expiration
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Authentication cookie settings
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # Local development: False
    # Production with HTTPS: True
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None

    # Password setup and reset links.
    # FRONTEND_BASE_URL is the web app's public address, used to build the
    # links in account emails. It must be https:// except for localhost.
    # Password emails are not sent until it is set.
    FRONTEND_BASE_URL: str | None = None
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    PASSWORD_SETUP_TOKEN_EXPIRE_HOURS: int = 72

    # Rate limits for password endpoints, per rolling window.
    PASSWORD_RATE_LIMIT_WINDOW_SECONDS: int = 900
    PASSWORD_RESET_REQUESTS_PER_EMAIL: int = 3
    PASSWORD_RESET_REQUESTS_PER_IP: int = 10
    PASSWORD_TOKEN_ATTEMPTS_PER_IP: int = 20

    # Outgoing email (SMTP). Email is disabled until SMTP_HOST and
    # EMAIL_FROM are set.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_STARTTLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: float = 10.0
    EMAIL_FROM: str | None = None
    EMAIL_FROM_NAME: str = "Kitchen Copilot"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
