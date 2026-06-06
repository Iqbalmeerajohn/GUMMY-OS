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

# The first version number assigned to a newly created memory.
INITIAL_VERSION_NUMBER = 1

# ── Embeddings & semantic search ──────────────────────────────────────────────
# Lightweight, CPU-friendly sentence encoder. 384-dim, strong retrieval quality,
# zero per-call cost. The DB vector column dimension is fixed to this value, so
# changing it requires a migration.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

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
