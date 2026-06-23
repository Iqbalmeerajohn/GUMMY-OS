"""Shared constants and tunable defaults.

Day 3 uses flat score defaults; real importance/confidence scoring lands on a
later day (see docs/phase-1-build-plan.md §5). Pagination bounds are enforced at
the API edge.
"""

from __future__ import annotations

# Default memory scores when the caller does not supply them.
DEFAULT_IMPORTANCE_SCORE = 0.5
DEFAULT_CONFIDENCE_SCORE = 0.5

# Score bounds (also enforced by DB CHECK constraints and schema validation).
MIN_SCORE = 0.0
MAX_SCORE = 1.0

# Memory content length bounds.
MIN_CONTENT_LENGTH = 1
MAX_CONTENT_LENGTH = 10_000

# Pagination.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

# ── Conversations (Phase 2) ───────────────────────────────────────────────────
# Title bound; titles are short labels (auto-generated or user-edited).
CONVERSATION_TITLE_MAX_LENGTH = 200
# How many recent messages from the thread to replay as working memory in a turn.
# A count cap for M4; token-budgeted trimming is a later refinement.
DEFAULT_TURN_HISTORY_MESSAGES = 20

# Rolling-summary trigger (PHASE2_PLAN.md §21 Q2): token-pressure primary, with a
# message-count safety cap. A refresh fires when the unsummarized delta exceeds
# EITHER threshold.
SUMMARY_TRIGGER_TOKEN_THRESHOLD = 500
SUMMARY_TRIGGER_MESSAGE_COUNT = 6
# Cap on how many delta messages are rendered into one summarization prompt.
SUMMARY_MAX_DELTA_MESSAGES = 100

# Extraction (Phase 2, M6) reuses the summary trigger cadence (same delta window);
# this caps how many memories one extraction pass may create.
EXTRACTION_MAX_MEMORIES = 10

# ── Conversation search (Phase 2, M7) ─────────────────────────────────────────
# Hybrid blend of keyword (messages full-text) and semantic (summary embeddings).
# Weights sum to 1.0 so the final score stays in [0, 1].
CONVERSATION_SEARCH_KEYWORD_WEIGHT = 0.5
CONVERSATION_SEARCH_SEMANTIC_WEIGHT = 0.5

# The first version number assigned to a newly created memory.
INITIAL_VERSION_NUMBER = 1

# ── Embeddings & semantic search ──────────────────────────────────────────────
# Lightweight, CPU-friendly sentence encoder. 384-dim, strong retrieval quality,
# zero per-call cost. The DB vector column dimension is fixed to this value, so
# changing it requires a migration.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# Default (production) embedding provider model. OpenAI's text-embedding-3-small
# supports the `dimensions` request param, so we ask for EMBEDDING_DIMENSION (384)
# to match the existing pgvector column — no schema migration, no torch/CUDA.
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
# Default OpenAI chat model (used when LLM_PROVIDER=openai). Cheap + capable.
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"

# Semantic search result bounds.
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 50

# ── Hybrid retrieval ──────────────────────────────────────────────────────────
# Weights blend the four ranking signals; they sum to 1.0 so the final score
# stays in [0, 1]. Semantic relevance dominates (is this memory about the query?)
# while importance/recency/confidence break ties and surface what matters.
RETRIEVAL_WEIGHT_SEMANTIC = 0.55
RETRIEVAL_WEIGHT_IMPORTANCE = 0.20
RETRIEVAL_WEIGHT_RECENCY = 0.15
RETRIEVAL_WEIGHT_CONFIDENCE = 0.10

# Recency half-life: a memory's recency score halves every N days.
RECENCY_HALF_LIFE_DAYS = 30.0

DEFAULT_RETRIEVAL_LIMIT = 10
MAX_RETRIEVAL_LIMIT = 50
# Over-fetch this many × the final limit as candidates, then re-rank.
RETRIEVAL_CANDIDATE_MULTIPLIER = 4

# ── Reinforcement (retrieving a memory makes it "stickier") ───────────────────
# Diminishing steps: new = old + STEP * (1 - old), hard-capped at 1.0.
IMPORTANCE_REINFORCEMENT_STEP = 0.05
CONFIDENCE_REINFORCEMENT_STEP = 0.03
# Score bumps happen at most once per cooldown window (anti-inflation safeguard).
REINFORCEMENT_COOLDOWN_SECONDS = 60

# ── Embedding background worker ───────────────────────────────────────────────
EMBEDDING_MAX_RETRIES = 3
EMBEDDING_RETRY_BASE_DELAY_SECONDS = 0.5

# ── Context assembly & chat ───────────────────────────────────────────────────
# Rough heuristic for token estimation without calling the model's tokenizer.
APPROX_CHARS_PER_TOKEN = 4
# Token budget for the memory context packed into a chat prompt.
DEFAULT_CONTEXT_TOKEN_BUDGET = 2000
# Upper bound on how many memories the retriever feeds into context assembly.
DEFAULT_CONTEXT_MAX_MEMORIES = 20

# ── Agent Framework (Phase 3) ─────────────────────────────────────────────────
# Per-run guards: an orchestration may dispatch at most this many agent steps
# and spend at most this many tokens before it is halted (runaway-loop/cost
# protection; PHASE3_PLAN.md §9.8/§12).
AGENT_MAX_RUN_STEPS = 8
AGENT_MAX_RUN_COST_TOKENS = 60_000
# Preview length for message/reply snippets stored on trace rows (keeps JSONB
# rows lean; full text lives on the messages table).
AGENT_TRACE_PREVIEW_CHARS = 200
# Context-pack caps for the Goal & Task Foundation (M8): how many active
# goals / open tasks are surfaced to an agent per dispatch.
CONTEXT_MAX_GOALS = 5
CONTEXT_MAX_TASKS = 10
# How long a pending action approval stays decidable (M10). After this it
# can only expire — stale previews must never be approvable.
ACTION_APPROVAL_TTL_SECONDS = 24 * 60 * 60

# ── LLM gateway defaults (Claude / Anthropic) ─────────────────────────────────
# Chat-facing default model. Configurable; the tiered fast/smart/frontier model
# ids support the project's cost-tiering strategy (see tech-stack.md §7).
DEFAULT_CHAT_MODEL = "claude-opus-4-8"
DEFAULT_CLAUDE_MODEL_FAST = "claude-haiku-4-5"
DEFAULT_CLAUDE_MODEL_SMART = "claude-sonnet-4-6"
DEFAULT_CLAUDE_MODEL_FRONTIER = "claude-opus-4-8"
DEFAULT_CHAT_MAX_TOKENS = 2048
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
DEFAULT_LLM_MAX_RETRIES = 2

# ── Files System (M6) ─────────────────────────────────────────────────────────
# Upload size ceiling (bytes). 25 MiB covers resumes, notes, and typical PDFs
# while bounding storage and processing cost. Enforced at the API edge.
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
# Deterministic chunking: target chunk size and overlap in characters. Character
# windows keep chunking dependency-free and reproducible; embeddings are derived
# later by the RAG layer, so we do not tokenize here. Overlap preserves context
# across chunk boundaries for future retrieval quality.
FILE_CHUNK_SIZE_CHARS = 1200
FILE_CHUNK_OVERLAP_CHARS = 150
# Rough chars→tokens divisor (shared heuristic, see APPROX_CHARS_PER_TOKEN) used
# to record an approximate token_count per chunk without a tokenizer call.
FILE_CHUNK_TOKEN_DIVISOR = 4
# Supported upload MIME types (MVP). CSV/XLSX are included as cheap extras.
# Maps canonical MIME → human label, used for validation and listing.
SUPPORTED_FILE_MIME_TYPES: dict[str, str] = {
    "application/pdf": "PDF",
    "text/plain": "Text",
    "text/markdown": "Markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("Word"),
    "text/csv": "CSV",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("Excel"),
}
# How many recently-uploaded files surface in agent context (metadata only —
# never file content; see context_builder).
CONTEXT_MAX_FILES = 10

# ── File Intelligence (M6.5) ──────────────────────────────────────────────────
# How many file chunks are injected into a prompt as grounding content. A turn
# budget that keeps the file context useful without crowding out memory/goals.
FILE_CONTEXT_MAX_CHUNKS = 8
# Over-fetch this many × the final chunk limit as keyword candidates, then
# re-rank by term-match count in the service (DB-portable ranking).
FILE_CONTEXT_CANDIDATE_MULTIPLIER = 4
# Minimum length of a query token to be treated as a search term (drops "a",
# "is", "of"-style noise without a full stopword list).
FILE_SEARCH_MIN_TERM_LENGTH = 3
# Max characters of a single chunk rendered into the prompt (defensive cap so a
# pathologically long chunk can't blow the context budget).
FILE_CONTEXT_CHUNK_CHAR_CAP = 1500

# ── Ollama (local inference) ──────────────────────────────────────────────────
# Local, self-hosted models served by Ollama (https://ollama.com). No API key
# and no per-call cost; selected via LLM_PROVIDER=ollama.
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
# A small, fast instruction model is the default chat/general-agent model: qwen3
# is an 8B reasoning model that emits <think> traces and is slow on CPU, whereas
# qwen2.5:3b answers directly, follows the JSON extraction prompt well, and is
# several times faster per turn. Override with OLLAMA_MODEL.
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
# Local models are far slower than a hosted API: even a small model on CPU can
# exceed the 30s Claude default for a single non-streaming turn. Because the
# whole generation arrives in one response body, this is effectively the HTTP
# read timeout. Generous by default; override with OLLAMA_TIMEOUT_SECONDS.
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120.0
