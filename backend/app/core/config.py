import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DonnaAI API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"

    # Database
    database_url: str = "sqlite:///./donnaai.db"
    sql_echo: bool = False

    # Session / JWT
    session_secret_key: str = "dev-session-secret-key-change-me-32"
    session_cookie_name: str = "donna_session"
    session_expire_minutes: int = 60 * 24 * 7
    session_cookie_secure: bool = False

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # Google OAuth 2.0
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # Spotify OAuth 2.0
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/api/v1/auth/spotify/callback"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Groq (OpenAI-compatible)
    groq_api_key: str = ""
    fallback_groq_api_key: str = ""
    fallback_groq_api_ke_2: str = ""

    # Google Gemini
    google_api_key: str = ""

    # Gmail Push (Pub/Sub)
    gmail_pubsub_topic: str = ""
    gmail_webhook_url: str = ""

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
