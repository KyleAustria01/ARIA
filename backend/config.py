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

    # LLM providers (fallback: cerebras → groq → bedrock → gemini → ollama)
    cerebras_api_key: str = Field("", env="CEREBRAS_API_KEY")
    groq_api_key: str = Field("", env="GROQ_API_KEY")
    gemini_api_key: str = Field("", env="GEMINI_API_KEY")
    ollama_base_url: str = Field("http://localhost:11434", env="OLLAMA_BASE_URL")

    # AWS Bedrock
    aws_access_key_id: str = Field("", env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field("", env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field("ap-southeast-1", env="AWS_REGION")
    aws_bedrock_model_id: str = Field(
        "amazon.nova-lite-v1:0",
        env="AWS_BEDROCK_MODEL_ID",
    )
    aws_bedrock_api_key: str = Field("", env="AWS_BEDROCK_API_KEY")

    # STT
    # groq whisper uses groq_api_key above
    # faster-whisper runs locally — no key needed

    # TTS — edge-tts (free, no key needed)

    # Web search
    tavily_api_key: str = Field("", env="TAVILY_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
