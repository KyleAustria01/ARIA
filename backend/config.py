"""
Configuration loader for ARIA MVP 2.0.

Loads all settings from environment variables / .env file.
All secrets are optional with sensible defaults for development.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables."""

    # App
    secret_key: str = Field("aria-change-this-in-production", env="SECRET_KEY")
    app_env: str = Field("development", env="APP_ENV")
    frontend_url: str = Field("http://localhost:3000", env="FRONTEND_URL")

    # Redis
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")
    redis_ttl_hours: int = Field(24, env="REDIS_TTL_HOURS")

    # LLM providers (fallback: cerebras → groq → gemini → ollama)
    cerebras_api_key: str = Field("", env="CEREBRAS_API_KEY")
    groq_api_key: str = Field("", env="GROQ_API_KEY")
    gemini_api_key: str = Field("", env="GEMINI_API_KEY")
    ollama_base_url: str = Field("http://localhost:11434", env="OLLAMA_BASE_URL")

    # STT
    # groq whisper uses groq_api_key above
    # faster-whisper runs locally — no key needed

    # TTS — ElevenLabs (primary), pyttsx3 offline fallback
    elevenlabs_api_key: str = Field("", env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", env="ELEVENLABS_VOICE_ID")

    # Web search
    tavily_api_key: str = Field("", env="TAVILY_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
