"""Chunking that respects segment boundaries and keeps provenance attached.

The window-over-concatenation approach that preceded this produced chunks
spanning two pages or two unrelated headings, which made every citation derived
from them approximate. Chunking within a segment is what lets a chunk claim a
location at all.
"""

from __future__ import annotations

from app.services.files.chunking_service import chunk_segments
from app.services.files.extraction_service import DocumentSegment

CSV_HEADER = "name,role,year"
LONG_ROWS = "\n".join(f"person{i},engineer,2024" for i in range(200))


def _segment(content: str, **kw: object) -> DocumentSegment:
    return DocumentSegment(content=content, **kw)  # type: ignore[arg-type]


def test_chunks_never_span_two_segments() -> None:
    """A chunk covering two pages could not honestly cite either."""
    segments = [
        _segment("alpha " * 200, page=1),
        _segment("beta " * 200, page=2),
    ]
    for chunk in chunk_segments(segments, chunk_size=300, overlap=50):
        assert not ("alpha" in chunk.content and "beta" in chunk.content)


def test_each_chunk_inherits_its_segment_location() -> None:
    segments = [_segment("alpha " * 200, page=1), _segment("beta " * 200, page=2)]
    for chunk in chunk_segments(segments, chunk_size=300, overlap=50):
        expected = 1 if "alpha" in chunk.content else 2
        assert chunk.as_metadata()["page"] == expected


def test_chunk_indices_are_contiguous_across_segments() -> None:
    """A gap in the sequence means a chunk was dropped somewhere."""
    segments = [_segment("alpha " * 200, page=1), _segment("beta " * 200, page=2)]
    indices = [c.index for c in chunk_segments(segments, chunk_size=300, overlap=50)]
    assert indices == list(range(len(indices)))


def test_csv_header_is_repeated_on_every_chunk() -> None:
    segments = [
        _segment(LONG_ROWS, header=CSV_HEADER, row_start=2, row_end=201),
    ]
    chunks = list(chunk_segments(segments, chunk_size=400, overlap=40))
    assert len(chunks) > 1, "fixture must be long enough to split"
    for chunk in chunks:
        assert chunk.content.startswith(CSV_HEADER)


def test_repeated_header_does_not_push_chunks_over_the_size_limit() -> None:
    """The prefix has to come out of the budget, not be added on top of it."""
    size = 400
    segments = [_segment(LONG_ROWS, header=CSV_HEADER, row_start=2, row_end=201)]
    for chunk in chunk_segments(segments, chunk_size=size, overlap=40):
        assert len(chunk.content) <= size


def test_metadata_omits_locations_the_segment_does_not_have() -> None:
    """Absent provenance must be absent, not null-filled or guessed."""
    chunks = list(chunk_segments([_segment("plain text")], chunk_size=300, overlap=0))
    assert chunks[0].as_metadata() == {}


def test_chunking_is_deterministic() -> None:
    segments = [_segment("alpha " * 200, page=1)]
    first = [c.content for c in chunk_segments(segments, chunk_size=300, overlap=50)]
    second = [c.content for c in chunk_segments(segments, chunk_size=300, overlap=50)]
    assert first == second


def test_empty_segments_produce_no_chunks() -> None:
    assert list(chunk_segments([_segment("   ")], chunk_size=300, overlap=0)) == []
