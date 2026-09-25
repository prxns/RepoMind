from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://repomind:repomind@localhost:5432/repomind"
    github_token: SecretStr = SecretStr("")
    github_api_url: str = "https://api.github.com"
    llm_provider: str = "auto"
    gemini_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GEMINI_API_KEY", "LLM_API_KEY"),
    )
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1/interactions"
    gemini_primary_model: str = "gemini-3.8-flash"
    gemini_secondary_model: str = "gemini-3.7-flash"
    gemini_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    reranker_provider: str = "token_overlap"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = Field(default=30, ge=1)
    global_rate_limit_per_minute: int = Field(default=120, ge=1)
    max_active_ingestions: int = Field(default=8, ge=1)
    max_concurrent_queries: int = Field(default=4, ge=1)
    max_files: int = 5000
    max_file_bytes: int = 524288
    max_total_bytes: int = 26214400
    max_chunks: int = 25000
    chunk_target_lines: int = 80
    chunk_overlap_lines: int = 12
    max_context_chars: int = 18000
    evidence_gate_min_score: float = Field(default=0.30, ge=0, le=1)
    evidence_gate_min_signals: int = Field(default=2, ge=1, le=4)
    evidence_gate_min_query_terms: int = Field(default=1, ge=1)
    evidence_gate_min_lexical_coverage: float = Field(default=0.20, ge=0, le=1)
    evidence_gate_min_dense_similarity: float = Field(default=0.25, ge=-1, le=1)
    evidence_gate_min_rank_agreement: float = Field(default=0.20, ge=0, le=1)
    evidence_gate_min_reranker_overlap: float = Field(default=0.20, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
