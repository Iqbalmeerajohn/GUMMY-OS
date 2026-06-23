"""Unit tests for the M6 processing pipeline: chunking + text extraction.

Chunking must be deterministic and gap-free; extraction must handle every MVP
format and fail cleanly on unsupported types. No database here — pure logic.
"""

from __future__ import annotations

import io

import pytest

from app.core.constants import (
    FILE_CHUNK_OVERLAP_CHARS,
    FILE_CHUNK_SIZE_CHARS,
)
from app.services.files import chunking_service, extraction_service
from app.services.files.extraction_service import (
    ExtractionError,
    UnsupportedFileTypeError,
)

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument" ".wordprocessingml.document"
)


# ── Chunking ──────────────────────────────────────────────────────────────────


def test_chunk_text_empty_yields_nothing() -> None:
    assert chunking_service.chunk_text("") == []
    assert chunking_service.chunk_text("   \n\t ") == []


def test_chunk_text_short_single_chunk() -> None:
    chunks = chunking_service.chunk_text("hello world")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "hello world"
    assert chunks[0].token_count >= 1


def test_chunk_text_is_deterministic() -> None:
    text = "alpha beta gamma " * 500
    first = chunking_service.chunk_text(text)
    second = chunking_service.chunk_text(text)
    assert [c.content for c in first] == [c.content for c in second]
    assert [c.index for c in first] == [c.index for c in second]


def test_chunk_text_indices_are_gap_free_and_ordered() -> None:
    text = "x" * (FILE_CHUNK_SIZE_CHARS * 3)
    chunks = chunking_service.chunk_text(text)
    assert len(chunks) >= 3
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_text_windows_overlap() -> None:
    # Distinct characters so overlap is observable at the boundary.
    text = "".join(chr(33 + (i % 90)) for i in range(FILE_CHUNK_SIZE_CHARS * 2))
    chunks = chunking_service.chunk_text(text)
    assert len(chunks) >= 2
    step = FILE_CHUNK_SIZE_CHARS - FILE_CHUNK_OVERLAP_CHARS
    # Second chunk starts `step` chars in, so it shares the overlap tail.
    assert chunks[1].start_offset == step


def test_chunk_text_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        chunking_service.chunk_text("abc", chunk_size=0)
    with pytest.raises(ValueError):
        chunking_service.chunk_text("abc", chunk_size=10, overlap=10)


# ── Extraction ─────────────────────────────────────────────────────────────────


def test_extract_plaintext() -> None:
    text = extraction_service.extract_text(data=b"hello\nworld", mime_type="text/plain")
    assert text == "hello\nworld"


def test_extract_markdown() -> None:
    text = extraction_service.extract_text(
        data=b"# Title\n\nbody", mime_type="text/markdown"
    )
    assert "Title" in text


def test_extract_csv_flattens_rows() -> None:
    text = extraction_service.extract_text(data=b"a,b,c\n1,2,3", mime_type="text/csv")
    assert "a, b, c" in text
    assert "1, 2, 3" in text


def test_extract_unsupported_type_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        extraction_service.extract_text(data=b"\x00\x01", mime_type="image/png")


def test_extract_pdf_roundtrip() -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # A blank PDF extracts to empty text but must not raise.
    text = extraction_service.extract_text(
        data=buf.getvalue(), mime_type="application/pdf"
    )
    assert isinstance(text, str)


def test_extract_docx_roundtrip() -> None:
    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("Resume of a test candidate")
    document.add_paragraph("Skills: Python, FastAPI")
    buf = io.BytesIO()
    document.save(buf)
    text = extraction_service.extract_text(data=buf.getvalue(), mime_type=_DOCX_MIME)
    assert "Resume of a test candidate" in text
    assert "FastAPI" in text


def test_extract_corrupt_pdf_raises_extraction_error() -> None:
    pytest.importorskip("pypdf")
    with pytest.raises(ExtractionError):
        extraction_service.extract_text(
            data=b"%PDF-1.4 not really a pdf",
            mime_type="application/pdf",
        )
