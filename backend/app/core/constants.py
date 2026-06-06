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
