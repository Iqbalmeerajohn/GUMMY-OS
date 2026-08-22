"""The relevance floor, pinned to the measurement that produced it.

``FILE_RETRIEVAL_MIN_SIMILARITY`` is the difference between "I found nothing
relevant" being expressible and every question returning the nearest three
chunks of whatever the user happens to own. It was calibrated by embedding real
document chunks with nomic-embed-text and scoring labelled query pairs; the
observed statistics are recorded here so the constant cannot drift away from the
evidence for it without a test failing.

These are the summary statistics, not the raw fixtures: reproducing them needs a
running Ollama, which unit tests must not require. The generating script and its
full output live in docs/KNOWLEDGE_RAG.md.
"""

from __future__ import annotations

from app.core.constants import FILE_RETRIEVAL_MIN_SIMILARITY
from app.services.files.hybrid_retrieval import RetrievedChunk, _passes_gate

# Measured with nomic-embed-text over 12 chunks from three fixture documents.
# Relevant: best in-document similarity for a query the document answers.
# Distractor: best similarity in the OTHER documents for that same query.
# No-answer: best similarity anywhere for a query no document answers.
RELEVANT_MIN, RELEVANT_MEDIAN = 0.480, 0.613
DISTRACTOR_MAX = 0.494
NO_ANSWER_MEDIAN, NO_ANSWER_MAX = 0.430, 0.505


def _result(similarity: float, *, matched_text: bool = False) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=None,  # type: ignore[arg-type]  # the gate only reads similarity
        filename="fixture.md",
        similarity=similarity,
        score=0.0,
        matched_vector=True,
        matched_text=matched_text,
    )


def test_floor_sits_between_the_measured_distributions() -> None:
    """Above every distractor, below the median relevant pair."""
    assert DISTRACTOR_MAX < FILE_RETRIEVAL_MIN_SIMILARITY < RELEVANT_MEDIAN


def test_floor_rejects_every_cross_document_distractor() -> None:
    """A query answered by one document must not drag in the others."""
    assert not _passes_gate(_result(DISTRACTOR_MAX), FILE_RETRIEVAL_MIN_SIMILARITY)


def test_floor_rejects_typical_no_answer_queries() -> None:
    """The case the gate exists for: nothing owned relates to the question."""
    assert not _passes_gate(_result(NO_ANSWER_MEDIAN), FILE_RETRIEVAL_MIN_SIMILARITY)


def test_floor_keeps_typical_relevant_chunks() -> None:
    assert _passes_gate(_result(RELEVANT_MEDIAN), FILE_RETRIEVAL_MIN_SIMILARITY)


def test_known_overlap_is_documented_not_solved() -> None:
    """The distributions overlap; this records it rather than pretending.

    One no-answer query scored 0.505 and the weakest relevant pair 0.480, so a
    similarity floor alone cannot be both complete and precise. Should a future
    embedding model separate them, this test fails and the floor should be
    retuned to exploit the cleaner split.
    """
    assert RELEVANT_MIN < NO_ANSWER_MAX, "distributions now separate — recalibrate"


def test_lexical_hits_bypass_the_floor() -> None:
    """A chunk containing the literal words is evidence regardless of cosine.

    This is what keeps recall usable despite a floor above some true positives:
    the weakest relevant pair in calibration lost to the floor on vector score,
    and the lexical channel is the path that still reaches chunks like it.
    """
    assert _passes_gate(_result(0.05, matched_text=True), FILE_RETRIEVAL_MIN_SIMILARITY)
