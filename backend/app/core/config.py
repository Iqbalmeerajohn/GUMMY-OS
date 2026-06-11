"""Application settings.

Settings are loaded from environment variables (and a local ``.env`` file in the
backend working directory) via pydantic-settings. Unknown keys are ignored so the
shared root ``.env.example`` can hold variables for later days/phases without
breaking Day 1. Secrets default to ``None`` so the app boots in development before
every integration is wired up.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.core.constants import (
    DEFAULT_CHAT_MAX_TOKENS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CLAUDE_MODEL_FAST,
    DEFAULT_CLAUDE_MODEL_FRONTIER,
    DEFAULT_CLAUDE_MODEL_SMART,
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    EMBEDDING_DIMENSION,
)

# Substring marking the placeholder DATABASE_URL shipped in `.env.example`. When
# present we treat the database as "not configured" so Day 1 runs without a DB.
_DB_PLACEHOLDER = "password@localhost"


def _normalize_asyncpg(url: str) -> str:
    """Rewrite a Postgres URL to the SQLAlchemy asyncpg driver."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ──────────────────────────────────────────────────────────────────
    app_name: str = "GUMMY OS"
    app_env: str = "development"
    log_level: str = "info"
    version: str = __version__

    # ── Backend / HTTP ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"  # noqa: S104 - container binds all interfaces
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"
    secret_key: str = "dev-insecure-change-me"

    # ── Database (wired for readiness checks; ORM models land Day 2) ──────────
    database_url: str | None = None
    direct_database_url: str | None = None

    # ── Supabase (used from Day 2+) ───────────────────────────────────────────
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None

    # ── Authentication (Phase 1.5) ────────────────────────────────────────────
    # JWTs are verified locally (HS256) with `supabase_jwt_secret`. The algorithm
    # list is a config seam for future JWKS/RS256 — comma-separated, HS256 today.
    auth_enabled: bool = True
    auth_dev_bypass: bool = False  # MUST stay false in production (startup guard)
    auth_dev_user_id: uuid.UUID | None = None
    supabase_jwt_aud: str = "authenticated"
    supabase_jwt_algorithms: str = "HS256"

    # ── AI (used from Day 3+) ─────────────────────────────────────────────────
    anthropic_api_key: str | None = None

    # ── Embeddings / semantic search ──────────────────────────────────────────
    # provider: "huggingface" (real, local model) | "fake" (deterministic, dev/tests)
    embeddings_provider: str = "huggingface"
    embeddings_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = EMBEDDING_DIMENSION

    # ── LLM gateway (Claude / Anthropic) ──────────────────────────────────────
    # provider: "claude" (real) | "fake" (dev/tests). Future: openai, gemini.
    llm_provider: str = "claude"
    claude_model: str = DEFAULT_CHAT_MODEL
    claude_model_fast: str = DEFAULT_CLAUDE_MODEL_FAST
    claude_model_smart: str = DEFAULT_CLAUDE_MODEL_SMART
    claude_model_frontier: str = DEFAULT_CLAUDE_MODEL_FRONTIER
    claude_max_tokens: int = DEFAULT_CHAT_MAX_TOKENS
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    llm_max_retries: int = DEFAULT_LLM_MAX_RETRIES

    # ── Context assembly ──────────────────────────────────────────────────────
    context_token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET
    context_max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES

    # ── Agent Framework (Phase 3) ─────────────────────────────────────────────
    # M3: when on, each turn is traced as a single-agent agent_run/agent_step
    # wrapping the unchanged Phase 2 reply call. Behavior-identical; off by
    # default until verified.
    agents_run_recording: bool = False
    # M4: when on, run_turn delegates the reply to the Master Orchestrator
    # (single general agent) with a guaranteed fallback to the legacy core.
    # Off by default until the parity + eval gates pass (M11 flips it).
    agents_orchestration_enabled: bool = False

    # ── Memory extraction consent (Phase 2 / memory-system §2) ────────────────
    # Gates the automatic conversation→memory extraction consumer. Safe default:
    # "assisted" persists nothing automatically (proposal surface is future work);
    # "autonomous" auto-saves; "explicit" disables automatic extraction entirely.
    memory_consent_mode: str = "assisted"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.lower()

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins parsed from the comma-separated env value."""
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def jwt_algorithms(self) -> list[str]:
        """Accepted JWT algorithms, parsed from the comma-separated env value."""
        return [a.strip() for a in self.supabase_jwt_algorithms.split(",") if a.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_database_configured(self) -> bool:
        """True only when a real (non-placeholder) DATABASE_URL is present."""
        url = self.database_url
        if not url:
            return False
        return _DB_PLACEHOLDER not in url

    @property
    def async_database_url(self) -> str | None:
        """DATABASE_URL normalized to the asyncpg driver, or None if unset."""
        url = self.database_url
        if not self.is_database_configured or url is None:
            return None
        return _normalize_asyncpg(url)

    @property
    def migration_async_url(self) -> str | None:
        """URL Alembic should use — prefers the direct (non-pooled) connection.

        Migrations run schema DDL and should bypass the transaction pooler, so we
        prefer DIRECT_DATABASE_URL and fall back to DATABASE_URL.
        """
        raw = self.direct_database_url or self.database_url
        if not raw or _DB_PLACEHOLDER in raw:
            return None
        return _normalize_asyncpg(raw)


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
