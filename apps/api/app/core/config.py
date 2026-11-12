"""모든 환경변수 정의 (설계서 9.1). 새 변수는 .env.example 과 함께 추가한다."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

DEFAULT_AUTH_SECRET = "change-me-32bytes-min"

# 8.3 검증 한도 (서버 고정)
QUERY_MIN_CHARS = 1
QUERY_MAX_CHARS = 1000
TOP_K_MIN = 1
TOP_K_MAX = 20
COLLECTION_IDS_MAX = 20
UPLOAD_MAX_MB = 20
UPLOAD_MAX_PAGES = 200
USERNAME_MIN = 3
USERNAME_MAX = 32
PASSWORD_MIN = 8
PASSWORD_MAX = 128

# 5.3 청킹 파라미터 (고정)
CHUNK_TARGET_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 60
CHUNK_MAX_TOKENS = 600
CHUNK_MIN_TOKENS = 20
CHUNKER_VERSION = "v1"
PARSER_VERSION = "pymupdf-v1"
PARSE_TIMEOUT_SECONDS = 60
PROMPT_VERSION = "v1"
EMBED_QUERY_TIMEOUT_SECONDS = 15  # 질문 임베딩 상한 (모델 적재 대기 포함)
OPENSEARCH_INDEX = "chunks_v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 서버 ---
    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_query_text: bool = False
    expose_docs: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    auth_secret: SecretStr = SecretStr(DEFAULT_AUTH_SECRET)
    auth_token_ttl_seconds: int = 28800
    seed_on_start: bool = True
    data_dir: Path = Path("/data")
    institutions_file: Path = Path("/app/config/institutions.yaml")
    users_file: Path = Path("/app/config/users.yaml")
    app_commit: str = "unknown"

    # --- 검색 엔진 ---
    qdrant_url: str = "http://qdrant:6333"
    opensearch_url: str = "http://opensearch:9200"
    keyword_analyzer: Literal["korean", "standard"] = "korean"
    search_engine_timeout_ms: int = 2000

    # --- 임베딩 ---
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 32
    openai_api_key: SecretStr = SecretStr("")
    openai_embedding_model: str = "text-embedding-3-small"

    # --- 답변 ---
    answer_provider: Literal["fake", "openai", "claude"] = "fake"
    openai_chat_model: str = ""
    anthropic_api_key: SecretStr = SecretStr("")
    claude_model: str = "claude-opus-5-5"
    answer_max_attempts: int = 2
    answer_timeout_seconds: int = 30

    # --- 캐시·한도 ---
    cache_embed_ttl_seconds: int = 3600
    cache_retrieval_ttl_seconds: int = 300
    cache_answer_enabled: bool = False
    rate_limit_enabled: bool = True
    rate_limit_query_per_minute: int = 30
    rate_limit_answers_per_minute: int = 10
    rate_limit_upload_per_hour: int = 20
    rerank_enabled: bool = False

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        secret = self.auth_secret.get_secret_value()
        if secret == DEFAULT_AUTH_SECRET or len(secret.encode()) < 32:
            if self.app_env == "prod":
                raise ValueError("AUTH_SECRET 이 기본값이거나 32바이트 미만이다. prod 에서는 기동할 수 없다.")
            log.warning("AUTH_SECRET 이 기본값이거나 32바이트 미만이다 (dev/test 에서만 허용)")
        if self.answer_provider == "openai":
            if not self.openai_api_key.get_secret_value():
                raise ValueError("ANSWER_PROVIDER=openai 인데 OPENAI_API_KEY 가 비어 있다.")
            if not self.openai_chat_model:
                raise ValueError("ANSWER_PROVIDER=openai 인데 OPENAI_CHAT_MODEL 이 비어 있다.")
        if self.answer_provider == "claude" and not self.anthropic_api_key.get_secret_value():
            raise ValueError("ANSWER_PROVIDER=claude 인데 ANTHROPIC_API_KEY 가 비어 있다.")
        if self.embedding_provider == "openai" and not self.openai_api_key.get_secret_value():
            raise ValueError("EMBEDDING_PROVIDER=openai 인데 OPENAI_API_KEY 가 비어 있다.")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'app.db'}"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def emb_cache_dir(self) -> Path:
        return self.data_dir / "emb_cache"

    @property
    def active_embedding_model(self) -> str:
        if self.embedding_provider == "openai":
            return self.openai_embedding_model
        return self.embedding_model

    def secret_values(self) -> list[str]:
        """로그 마스킹 대상 값."""
        vals = [
            self.openai_api_key.get_secret_value(),
            self.anthropic_api_key.get_secret_value(),
            self.auth_secret.get_secret_value(),
        ]
        return [v for v in vals if v]


@lru_cache
def get_settings() -> Settings:
    return Settings()
