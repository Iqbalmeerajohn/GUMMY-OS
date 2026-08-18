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
# Lightweight, CPU-friendly sentence encoder. Retained as the HF provider's
# default; it is 384-dim, so switching EMBEDDINGS_PROVIDER=hf now also requires
# EMBEDDING_DIMENSION=384 and a rebuilt database.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The width of every stored vector. pgvector columns are declared as
# ``Vector(EMBEDDING_DIMENSION)``, so this value IS the schema: changing it means
# rebuilding the database (locally: `docker compose down -v && alembic upgrade head`).
#
# 768 = nomic-embed-text, the local Ollama default. It measurably out-retrieves
# 384-dim MiniLM, and recall accuracy is the core of this product, so the wider
# column is worth its storage.
EMBEDDING_DIMENSION = 768

# ── Ollama (local inference; LLM_PROVIDER/EMBEDDINGS_PROVIDER=ollama) ─────────
# nomic-embed-text: 768-dim, 274MB, runs on CPU or GPU in milliseconds.
DEFAULT_OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
# How long Ollama keeps a model resident after its last request. The default is
# 5 minutes, which means a user returning after a coffee break pays a multi-second
# cold load on their first message. 30m keeps the model warm through normal use,
# which is what makes sub-second first-token latency reachable.
DEFAULT_OLLAMA_KEEP_ALIVE = "30m"

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

# ── Relevance floor ───────────────────────────────────────────────────────────
# The minimum SEMANTIC similarity a memory must reach before it may enter the
# model's context. Applied to the raw similarity, deliberately — not to the
# blended score — because importance, confidence, and recency together carry 45%
# of the blend, which is enough to lift a memory with no topical relationship to
# the question into the top N. Without this floor, "what is the capital of
# France?" pulls in whatever the user's most important recent memories happen to
# be, and the assistant volunteers them. That is the memory-spam failure mode.
#
# 0.45 is measured, not guessed. Against the live store (nomic-embed-text, the
# same /api/embed call the provider makes) over 11 probe queries × 9 stored
# memories — 12 relevant pairs, 87 irrelevant:
#
#     irrelevant pairs   mean 0.362   max 0.468
#     relevant pairs     mean 0.533   min 0.429
#
#     floor   relevant kept   irrelevant kept
#      0.45      11/12  (92%)     3/87  (3.4%)
#      0.50       7/12  (58%)     0/87  (0%)
#
# The distributions overlap slightly, so no threshold is perfect. 0.45 sits just
# above the bulk of the irrelevant mass while keeping nearly every real match;
# 0.50 buys the last 3% of precision by discarding 42% of genuine recall, which
# is the worse trade — a forgetful assistant is a more visible failure than an
# occasional stray fact. Retune with scripts/calibrate_relevance.py if the
# embedding model changes; this number is only valid for the model that produced it.
RETRIEVAL_MIN_SEMANTIC_SIMILARITY = 0.45

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

# ── Tool loop ─────────────────────────────────────────────────────────────────
# How many times one agent turn may call tools before it must answer with what
# it has. Each iteration is a full model round-trip, so this is a latency budget
# as much as a safety one: at ~2-3s per local generation, 4 iterations is
# already a ~12s worst case. Conservative on purpose — the common shape is one
# tool call, and a model that wants five is usually looping, not working.
MAX_TOOL_ITERATIONS = 4

# Tool calls permitted in a single model response. A model that emits a dozen
# parallel calls has misunderstood the task; executing them all multiplies both
# latency and the blast radius of that misunderstanding.
MAX_TOOL_CALLS_PER_STEP = 3
AGENT_MAX_RUN_COST_TOKENS = 60_000
# Preview length for message/reply snippets stored on trace rows (keeps JSONB
# rows lean; full text lives on the messages table).
AGENT_TRACE_PREVIEW_CHARS = 200
# Router (M8): minimum weighted keyword score a specialist must reach to win the
# route; below this the General agent answers (graceful degradation). A
# multi-word phrase match scores more than a single keyword.
AGENT_ROUTER_MIN_SCORE = 1
AGENT_ROUTER_PHRASE_WEIGHT = 2
AGENT_ROUTER_KEYWORD_WEIGHT = 1
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

# ── Unified Knowledge & Retrieval Engine (M7) ─────────────────────────────────
# The engine fuses three sources — memories, goals, files — into one ranked,
# token-budgeted context layer. Cross-source weights scale each source's native
# score onto a shared 0–1 axis so a memory, a goal, and a file chunk can be
# ranked against each other. They are deliberate priorities, not a probability
# distribution, so they need not sum to 1.0.
KNOWLEDGE_WEIGHT_MEMORY = 1.0
KNOWLEDGE_WEIGHT_GOAL = 1.0
KNOWLEDGE_WEIGHT_FILE = 1.0
# An attached file is something the user explicitly pointed at ("summarize this
# resume"), so it must dominate the ranking — this additive boost lifts attached
# file chunks above every retrieved memory/goal/unattached file.
KNOWLEDGE_ATTACHMENT_BOOST = 1.0
# Goal scoring (all in [0, 1], blended like the memory hybrid score):
#   * active goals get a baseline presence so they can surface for "what should
#     I work on?" style queries even with no semantic hook;
#   * priority rank (high/medium/low) and deadline proximity break ties.
KNOWLEDGE_GOAL_BASE_SCORE = 0.5
KNOWLEDGE_WEIGHT_GOAL_PRIORITY = 0.3
KNOWLEDGE_WEIGHT_GOAL_DEADLINE = 0.2
# A goal due within this many days scores full deadline-proximity (linearly
# decaying to 0 at the horizon); overdue goals also score full proximity.
KNOWLEDGE_GOAL_DEADLINE_HORIZON_DAYS = 30.0
# File chunks from keyword search carry no numeric score, so they are ranked by
# their retrieval order: the Nth chunk gets BASE * DECAY**N (gentle decay so the
# best keyword match leads without collapsing the tail to zero).
KNOWLEDGE_FILE_BASE_SCORE = 0.6
KNOWLEDGE_FILE_RANK_DECAY = 0.9
# Token budget for the whole unified <knowledge> block packed into a prompt.
# Sized to comfortably hold memory + goals + file grounding together.
KNOWLEDGE_CONTEXT_TOKEN_BUDGET = 2500
# Hard caps per source so no single source can crowd out the others after
# ranking (applied before the shared token budget).
KNOWLEDGE_MAX_MEMORIES = 12
KNOWLEDGE_MAX_GOALS = 5
KNOWLEDGE_MAX_FILES = 8
# Max characters of a file chunk rendered into the unified block (defensive cap,
# mirrors FILE_CONTEXT_CHUNK_CHAR_CAP).
KNOWLEDGE_FILE_CHUNK_CHAR_CAP = 1500

# ── Web search fusion (M8.5) ──────────────────────────────────────────────────
# Live web search is a *supplemental* knowledge source: it must never override
# the user's own knowledge, so its cross-source weight sits BELOW memory. With
# the base weights all 1.0, a search weight of 0.5 keeps the priority order
# attachments > files > goals > memories > search.
KNOWLEDGE_WEIGHT_SEARCH = 0.5
# Search hits carry no numeric score, so they rank by result order (like file
# chunks): the Nth hit gets BASE * DECAY**N.
KNOWLEDGE_SEARCH_BASE_SCORE = 0.6
KNOWLEDGE_SEARCH_RANK_DECAY = 0.9
# Hard cap on search hits fused into the knowledge block (applied before the
# shared token budget) and the default number requested from the provider.
KNOWLEDGE_MAX_SEARCH = 5
SEARCH_DEFAULT_LIMIT = 5
# Max characters of a search snippet rendered into the block (defensive cap).
KNOWLEDGE_SEARCH_SNIPPET_CHAR_CAP = 500

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
