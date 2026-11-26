"""Application settings, loaded from environment variables or a local .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    # Leave empty to use the OpenAI Agents SDK default model.
    solace_model: str | None = None
    # A smaller, faster model for the per-message risk check. Empty = same as above.
    solace_safety_model: str | None = None
    # Which country's crisis lines to show first (ISO 3166-1 alpha-2).
    solace_region: str = "LK"
    # Where conversation history is stored. ":memory:" keeps nothing on disk.
    solace_db_path: str = "data/solace.db"
    # Real-time voice (OpenAI Realtime API over WebRTC).
    solace_voice_model: str = "gpt-realtime-2.1"
    solace_transcribe_model: str = "gpt-transcribe"
    solace_voice: str = "marin"
    # Knowledge base search. Lower the score to use notes more often, raise it to be stricter.
    solace_embedding_model: str = "text-embedding-3-large"
    solace_knowledge_min_score: float = 0.24


@lru_cache
def get_settings() -> Settings:
    return Settings()
