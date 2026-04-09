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
    token_encryption_key: str = ""
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
    google_redirect_uri: str = "http://localhost:8010/api/v1/auth/google/callback"

    # Spotify OAuth 2.0
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8010/api/v1/auth/spotify/callback"

    # Slack OAuth 2.0
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_redirect_uri: str = "http://localhost:8010/api/v1/auth/slack/callback"
    slack_signing_secret: str = ""

    # Microsoft / Teams OAuth 2.0
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str = "http://localhost:8010/api/v1/auth/teams/callback"
    teams_graph_base_url: str = "https://graph.microsoft.com/v1.0"

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

    # News
    news_api_key: str = ""
    news_fetch_interval_minutes: int = 30

    # Daily briefing / notifications
    morning_briefing_hour_utc: int = 13

    # Voice providers (optional placeholders)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Gmail Push (Pub/Sub)
    gmail_pubsub_topic: str = ""
    gmail_webhook_url: str = ""

    # OpenClaw gateway integration
    openclaw_cli_path: str = "openclaw"
    openclaw_node_path: str = ""
    openclaw_profile: str = ""
    openclaw_workdir: str = ""
    openclaw_gateway_url: str = ""
    openclaw_gateway_token: str = ""
    openclaw_gateway_password: str = ""
    openclaw_gateway_timeout_ms: int = 30000

    # OpenClaw channel toggles and account mapping
    openclaw_enable_slack: bool = False
    openclaw_enable_teams: bool = False

    openclaw_whatsapp_channel: str = "whatsapp"
    openclaw_whatsapp_account_id: str = ""
    openclaw_slack_channel: str = "slack"
    openclaw_slack_account_id: str = ""
    openclaw_teams_channel: str = "teams"
    openclaw_teams_account_id: str = ""

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
