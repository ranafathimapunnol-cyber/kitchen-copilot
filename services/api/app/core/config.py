from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Kitchen Copilot API"
    APP_VERSION: str = "0.1.0"
    AGENT_ENABLED: bool = False

    # Gemini AI configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
