from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://repomind:repomind@localhost:5432/repomind"
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    llm_provider: str = "extractive"
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    reranker_provider: str = "token_overlap"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 30
    max_files: int = 5000
    max_file_bytes: int = 524288
    max_total_bytes: int = 26214400
    max_chunks: int = 25000
    chunk_target_lines: int = 80
    chunk_overlap_lines: int = 12
    max_context_chars: int = 18000


@lru_cache
def get_settings() -> Settings:
    return Settings()
