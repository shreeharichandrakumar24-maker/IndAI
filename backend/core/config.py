from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database connection string
    # Default provided so FastAPI can start even if .env is missing/empty
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/dbname"

    # LLM configuration (Phase A: self-configuring factory)
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: Optional[str] = None

    # Voice path (Jarvis tab): small fast model for spoken replies.
    # Empty = reuse LLM_MODEL. Must exist on the provider (Groq list).
    LLM_MODEL_VOICE: str = ""
    # Supabase Auth (login + roles). ANON_KEY is publishable by design.
    SUPABASE_URL: str = "https://qxhwsuzzdwjmpfdqwwri.supabase.co"
    SUPABASE_ANON_KEY: str = ""
    # DEV ONLY: AUTH_DISABLED=true skips all login checks (local dev bypass).
    # Never enable in production — every API becomes open.
    AUTH_DISABLED: bool = False
    # Worker prototype tokens. Generate a long random value, e.g.
    # python -c "import secrets; print(secrets.token_hex(32))".
    WORKER_TOKEN_SECRET: str = ""
    # DEV ONLY: employee name the bypass login views as (empty = all active
    # assignments, convenient for first demo; set a name to prove per-worker
    # scoping). Ignored unless AUTH_DISABLED=true.
    DEV_VIEW_AS: str = ""

    # LiveKit voice agent (Part C). Never logged or returned to clients.
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    VOICE_AGENT_NAME: str = "indai-voice"

    # Load from .env file
    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8", extra="ignore")

# Instantiate settings
settings = Settings()
