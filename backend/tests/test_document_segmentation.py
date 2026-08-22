"""Extraction into segments that remember where the text came from.

Extraction used to flatten every format into one string, which threw away the
only thing that makes a citation checkable. These tests pin the provenance each
format can supply — a PDF knows its pages, Markdown knows its headings, a CSV
knows its rows — and pin the honest absence of provenance for plain text, since
an invented page number is worse than none.
"""

from __future__ import annotations

from app.services.files.extraction_service import extract_segments

MARKDOWN = b"""# GUMMY OS

Intro paragraph.

## Memory System
Memories are embedded and gated by a relevance floor.

### Recall
Recall never mixes documents with memories.

## Knowledge
Documents are chunked and embedded.
"""

CSV = b"name,role,year\n" + b"".join(
    f"person{i},engineer,202{i % 5}\n".encode() for i in range(60)
)


def test_markdown_segments_carry_their_heading() -> None:
    segments = extract_segments(data=MARKDOWN, mime_type="text/markdown")
    sections = [s.section for s in segments if s.section]
    assert "Memory System" in sections
    assert "Knowledge" in sections


def test_markdown_segment_content_belongs_to_its_section() -> None:
    """A heading label is only useful if the text under it is actually there."""
    segments = extract_segments(data=MARKDOWN, mime_type="text/markdown")
    memory = next(s for s in segments if s.section == "Memory System")
    assert "relevance floor" in memory.content
    assert "Documents are chunked" not in memory.content


def test_csv_segments_record_their_row_range() -> None:
    segments = extract_segments(data=CSV, mime_type="text/csv")
    assert segments, "a 60-row CSV must produce at least one segment"
    for seg in segments:
        assert seg.row_start is not None
        assert seg.row_end is not None
        assert seg.row_end >= seg.row_start


def test_csv_segments_cover_every_row_without_gaps() -> None:
    """Rows falling between segments would be silently unsearchable."""
    segments = extract_segments(data=CSV, mime_type="text/csv")
    ranges = sorted((s.row_start, s.row_end) for s in segments)
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:], strict=False):
        assert next_start == prev_end + 1


def test_csv_segments_all_carry_the_header() -> None:
    """A chunk of bare values is unreadable without its column names."""
    segments = extract_segments(data=CSV, mime_type="text/csv")
    for seg in segments:
        assert seg.header is not None
        assert "role" in seg.header


def test_plain_text_claims_no_location_it_does_not_have() -> None:
    segments = extract_segments(data=b"just some notes", mime_type="text/plain")
    assert len(segments) == 1
    assert segments[0].page is None
    assert segments[0].section is None
    assert segments[0].row_start is None


def test_extraction_is_deterministic() -> None:
    """Re-indexing the same bytes must not reshuffle the document."""
    first = extract_segments(data=MARKDOWN, mime_type="text/markdown")
    second = extract_segments(data=MARKDOWN, mime_type="text/markdown")
    assert [(s.content, s.section) for s in first] == [
        (s.content, s.section) for s in second
    ]
