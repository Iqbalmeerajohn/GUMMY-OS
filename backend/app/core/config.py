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
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_KEEP_ALIVE,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_CHAT_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
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

    # ── Authentication ────────────────────────────────────────────────────────
    auth_enabled: bool = True
    auth_dev_bypass: bool = False  # MUST stay false in production (startup guard)
    auth_dev_user_id: uuid.UUID | None = None

    # ── Local auth (GUMMY is its own identity provider) ───────────────────────
    # GUMMY issues and verifies its own HS256 access tokens, so sign-in works
    # with no external service and no network — there is no second issuer.
    #
    # The signing secret. MUST be overridden per-environment: a shared default
    # would let anyone mint a valid token, so an unset secret in production is a
    # startup failure (see assert_auth_safe), not a warning.
    gummy_jwt_secret: str | None = None
    gummy_jwt_issuer: str = "gummy-os-local"
    # Short-lived access token + long-lived rotating refresh token. The access
    # token is a bearer credential with no revocation list, so its lifetime is
    # the blast radius of a leak; refresh tokens are stored hashed and revocable.
    gummy_access_token_ttl_minutes: int = 60
    gummy_refresh_token_ttl_days: int = 30

    # Owner mode: a single-user local install auto-authenticates as the owner so
    # the app is usable offline with no login wall. Unlike auth_dev_bypass, this
    # resolves a REAL persisted user (by gummy_owner_email), so memories written
    # in owner mode remain owned by the same account after sign-in is enabled.
    # Refused in production by assert_auth_safe.
    gummy_owner_mode: bool = False
    gummy_owner_email: str = "owner@gummy.local"

    # ── Google OAuth (optional; direct to Google, no middleman) ───────────────
    # Inactive unless BOTH the client id and secret are set, so the app boots and
    # runs fully without them — Google sign-in is an enhancement, not a gate.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Where the OAuth callback sends the browser once a session is minted.
    frontend_url: str = "http://localhost:3000"

    # ── AI (used from Day 3+) ─────────────────────────────────────────────────
    anthropic_api_key: str | None = None

    # ── Embeddings / semantic search ──────────────────────────────────────────
    # provider:
    #   "ollama" (local daemon, free, offline — the local-first default) |
    #   "openai" (hosted API — no torch/CUDA) |
    #   "hf"/"huggingface" (local sentence-transformers; requires the optional
    #       `embeddings` extra) |
    #   "fake" (deterministic, dev/tests)
    # HuggingFace (sentence-transformers + torch) is NEVER imported unless the
    # provider is hf/huggingface.
    embeddings_provider: str = "ollama"
    embeddings_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = EMBEDDING_DIMENSION
    # OpenAI embeddings (used when EMBEDDING_PROVIDER=openai).
    openai_api_key: str | None = None
    openai_embeddings_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL

    # ── LLM gateway ───────────────────────────────────────────────────────────
    # provider:
    #   "claude"/"anthropic" (Claude) | "openai" (OpenAI chat completions) |
    #   "ollama" (local, free, offline — the local-first default) |
    #   "fake" (dev/tests).
    llm_provider: str = "ollama"
    claude_model: str = DEFAULT_CHAT_MODEL
    claude_model_fast: str = DEFAULT_CLAUDE_MODEL_FAST
    claude_model_smart: str = DEFAULT_CLAUDE_MODEL_SMART
    claude_model_frontier: str = DEFAULT_CLAUDE_MODEL_FRONTIER
    claude_max_tokens: int = DEFAULT_CHAT_MAX_TOKENS
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    llm_max_retries: int = DEFAULT_LLM_MAX_RETRIES
    # OpenAI chat model (used when LLM_PROVIDER=openai; reuses openai_api_key /
    # openai_base_url above).
    openai_chat_model: str = DEFAULT_OPENAI_CHAT_MODEL

    # ── Ollama (local inference; LLM and/or embeddings) ───────────────────────
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    # Embedding model (used when EMBEDDINGS_PROVIDER=ollama). Its output width
    # MUST equal embedding_dimension — the provider asserts this on first use.
    ollama_embedding_model: str = DEFAULT_OLLAMA_EMBEDDING_MODEL
    # How long Ollama keeps a model in memory after its last request. Sent on
    # every call, so the warm window is continuously extended during a session.
    ollama_keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE
    # Separate from llm_timeout_seconds: local inference is much slower than the
    # hosted Claude API, so Ollama gets its own generous read timeout while
    # Claude keeps fast failure detection.
    ollama_timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS

    # ── Context assembly ──────────────────────────────────────────────────────
    context_token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET
    context_max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES

    # ── Agent Framework (Phase 3) ─────────────────────────────────────────────
    # M3: when on, each turn is traced as a single-agent agent_run/agent_step
    # wrapping the unchanged Phase 2 reply call. Behavior-identical; off by
    # default until verified.
    agents_run_recording: bool = False
    # M4→M11: run_turn delegates the reply to the Master Orchestrator with a
    # guaranteed fallback to the legacy core. Default ON since M11 (the seal):
    # the parity + eval gates passed, and a single env var reverts every turn
    # to the verified Phase 2 path (the legacy core is never deleted).
    agents_orchestration_enabled: bool = True
    # M5: when on, the Router escalates ambiguous intents to an LLM
    # classifier on the cheap model tier. Off by default — the rules-first
    # path is deterministic and free, and the general agent is a safe
    # catch-all (the plan's cost rationale, §6.9).
    agents_router_llm_fallback: bool = False
    # M8.5: live web search (Brave) fused into the knowledge engine for the
    # Research/Career/Learning specialists. Off by default (cost): requires both
    # this flag AND ``brave_api_key`` to be active. When inactive, search-worthy
    # queries answer from the user's own knowledge with no Search section (B10).
    agents_web_search_enabled: bool = False

    # ── Web search (M8.5; Brave Search API) ───────────────────────────────────
    # The single live-search backend. Kept per-environment (a real secret). When
    # unset, the offline DummySearchProvider stays active and no live search runs.
    brave_api_key: str | None = None

    # ── Memory extraction consent (Phase 2 / memory-system §2) ────────────────
    # Gates the automatic conversation→memory extraction consumer:
    #   "autonomous" — auto-saves clearly-durable facts (the default: a personal
    #     AI OS must remember facts like a birthday across conversations);
    #   "assisted"   — proposes but persists nothing automatically (the proposal
    #     surface is future work, so it currently saves nothing — durable facts
    #     are silently lost, which is why this is NOT the default);
    #   "explicit"   — disables automatic extraction entirely.
    memory_consent_mode: str = "autonomous"

    # ── Files System (M6) ─────────────────────────────────────────────────────
    # Storage backend for uploaded file bytes. "local" writes to the filesystem
    # under ``files_storage_dir`` (dev / single-node). The abstraction is
    # provider-agnostic by design — "r2" / "s3" plug in here later without
    # touching the service or API layers.
    files_storage_provider: str = "local"
    # Base directory for the local provider. Relative paths resolve against the
    # backend working directory; override per-environment.
    files_storage_dir: str = "var/files"

    # ── Observability (Langfuse — LLM/agent tracing) ──────────────────────────
    # Tracks every LLM call, token usage, latency, cost, and agent/retrieval
    # metadata. Fully disabled (a no-op) unless BOTH the public and secret keys
    # are set — GUMMY sends nothing anywhere by default. Point ``langfuse_host``
    # at a self-hosted instance to keep traces on the machine; sample_rate is 0–1.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str | None = None
    langfuse_sample_rate: float = 1.0

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.lower()

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins parsed from the comma-separated env value."""
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def langfuse_enabled(self) -> bool:
        """True only when both Langfuse keys are present (tracing active)."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def web_search_enabled(self) -> bool:
        """True only when live web search is on AND a Brave key is configured."""
        return bool(self.agents_web_search_enabled and self.brave_api_key)

    @property
    def google_oauth_enabled(self) -> bool:
        """True only when both Google OAuth credentials are configured."""
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def local_auth_secret(self) -> str:
        """The signing secret for GUMMY-issued tokens.

        Falls back to ``secret_key`` so a minimal local ``.env`` works, but the
        production guard in ``assert_auth_safe`` rejects either value being left
        at its insecure default.
        """
        return self.gummy_jwt_secret or self.secret_key

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
