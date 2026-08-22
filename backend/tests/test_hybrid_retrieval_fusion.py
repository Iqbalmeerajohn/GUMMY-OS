"""Fusion, gating and citation labels — the ranking logic, without a database.

These are pure functions over candidate lists, which is deliberate: the part of
retrieval that decides what reaches the model should be testable without
standing up pgvector.
"""

from __future__ import annotations

import uuid

from app.services.files.hybrid_retrieval import (
    RetrievedChunk,
    _fuse,
    _passes_gate,
    _to_tsquery_input,
    normalize_query,
)


class _Chunk:
    """Enough of a FileChunk for ranking: an identity and a position."""

    def __init__(self, name: str, *, index: int = 0, meta: dict | None = None):
        self.id = uuid.uuid5(uuid.NAMESPACE_OID, name)
        self.file_id = uuid.uuid5(uuid.NAMESPACE_DNS, name)
        self.chunk_index = index
        self.content = name
        self.metadata_json = meta or {}


def _result(**kw: object) -> RetrievedChunk:
    base = {
        "chunk": _Chunk("c"),
        "filename": "Doc.pdf",
        "similarity": 0.0,
        "score": 0.0,
        "matched_vector": False,
        "matched_text": False,
    }
    return RetrievedChunk(**{**base, **kw})  # type: ignore[arg-type]


# ── Query normalisation ───────────────────────────────────────────────────────


def test_normalize_collapses_whitespace() -> None:
    assert normalize_query("  what   is\n\tthis ") == "what is this"


def test_tsquery_input_drops_punctuation_rather_than_escaping_it() -> None:
    """An unescaped quote makes Postgres reject the whole query."""
    terms = _to_tsquery_input('what\'s the "budget" (approx)?')
    assert '"' not in terms and "(" not in terms
    assert "budget" in terms


def test_tsquery_input_is_empty_for_a_query_with_no_usable_terms() -> None:
    assert _to_tsquery_input("? ! .") == ""


# ── Fusion ────────────────────────────────────────────────────────────────────


def test_agreement_between_retrievers_outranks_a_single_strong_hit() -> None:
    """The whole reason two retrievers run: corroboration should win."""
    both, vector_only = _Chunk("both"), _Chunk("vector-only")
    fused = _fuse(
        [(vector_only, "A.pdf", 0.9), (both, "A.pdf", 0.8)],
        [(both, "A.pdf")],
    )
    assert fused[0].chunk is both


def test_fusion_marks_which_retrievers_found_each_chunk() -> None:
    v, t = _Chunk("v"), _Chunk("t")
    by_id = {r.chunk.id: r for r in _fuse([(v, "A", 0.5)], [(t, "A")])}
    assert by_id[v.id].matched_vector and not by_id[v.id].matched_text
    assert by_id[t.id].matched_text and not by_id[t.id].matched_vector


def test_a_chunk_found_twice_appears_once() -> None:
    c = _Chunk("shared")
    assert len(_fuse([(c, "A", 0.7)], [(c, "A")])) == 1


def test_ordering_is_deterministic_for_equal_scores() -> None:
    """Equal scores must not reshuffle between identical runs."""
    a, b = _Chunk("a", index=1), _Chunk("b", index=2)
    first = [r.chunk.id for r in _fuse([], [(a, "A"), (b, "A")])]
    second = [r.chunk.id for r in _fuse([], [(a, "A"), (b, "A")])]
    assert first == second


# ── Relevance gate ────────────────────────────────────────────────────────────


def test_lexical_hits_bypass_the_similarity_floor() -> None:
    """Containing the literal words is evidence in its own right."""
    assert _passes_gate(_result(matched_text=True, similarity=0.01), 0.5)


def test_semantic_only_hits_must_clear_the_floor() -> None:
    assert not _passes_gate(_result(matched_vector=True, similarity=0.49), 0.5)
    assert _passes_gate(_result(matched_vector=True, similarity=0.51), 0.5)


# ── Citation labels ───────────────────────────────────────────────────────────


def test_label_prefers_a_page_when_extraction_recorded_one() -> None:
    r = _result(chunk=_Chunk("c", meta={"page": 2}), filename="Resume.pdf")
    assert r.source_label == "Resume.pdf — page 2"


def test_label_falls_back_to_a_section_then_to_rows() -> None:
    section = _result(chunk=_Chunk("c", meta={"section": "Skills"}), filename="A.md")
    assert section.source_label == "A.md — Skills"
    rows = _result(
        chunk=_Chunk("c", meta={"row_start": 2, "row_end": 26}), filename="p.csv"
    )
    assert rows.source_label == "p.csv — rows 2–26"


def test_label_is_just_the_filename_when_there_is_no_location() -> None:
    """A plain .txt has no page, and inventing one would be worse than none."""
    assert _result(chunk=_Chunk("c"), filename="notes.txt").source_label == "notes.txt"
