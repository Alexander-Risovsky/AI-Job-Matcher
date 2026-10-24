"""Configuration: no credentials or personal details are committed."""
from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_embed_model: str = "nomic-embed-text:latest"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "candidate_profile"
    qdrant_vector_size: int = 768
    rag_top_k: int = 8
    retrieval_context_limit: int = 15000
    match_threshold: int = Field(70, ge=0, le=100)

    state_db: Path = Path("data/history.sqlite3")
    checkpoint_db: Path = Path("data/checkpoints.sqlite3")

    mcp_fetch_command: str = "uvx"
    mcp_fetch_args: list[str] = ["mcp-server-fetch"]
    mcp_fetch_timeout: float = 25.0
    mcp_fetch_max_chars: int = 14000
    mcp_fetch_allowed_domains: str = ""

    ingest_host: str = "127.0.0.1"
    ingest_port: int = 8000
    ingest_api_key: str = ""
    telethon_ingest_url: str = "http://127.0.0.1:8000/vacancies/ingest"
    tg_api_id: int | None = None
    tg_api_hash: str = ""
    tg_session: str = "data/telegram_reader"
    tg_allowed_chat_ids: str = ""
    tg_allowed_topics: dict[str, list[int]] = {}
    tg_bot_token: str = ""
    tg_target_chat_id: str = ""
    max_startup_unread_per_source: int = 0
    startup_send_delay_seconds: float = 0.15

    @property
    def allowed_chat_ids(self) -> set[int]:
        return {int(value.strip()) for value in self.tg_allowed_chat_ids.split(",") if value.strip()}

    @property
    def allowed_topics(self) -> dict[int, set[int]]:
        return {int(k): set(v) for k, v in self.tg_allowed_topics.items()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
