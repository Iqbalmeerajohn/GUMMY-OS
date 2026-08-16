"""Text extraction from uploaded file bytes (M6).

Maps a MIME type to a decoder and returns plain text ready for chunking.
Parser libraries (``pypdf``, ``python-docx``, ``openpyxl``) are imported lazily
inside their branch — exactly like the optional embeddings providers — so they
are only required when a user actually uploads that format. Any extraction
failure is raised as :class:`ExtractionError` (an ``AppError``) so the service
layer can mark the file ``failed`` and capture the error.
"""

from __future__ import annotations

import csv
import io
import logging

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# MIME types whose bytes are UTF-8 text and need no parser.
_PLAINTEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown"})


class ExtractionError(AppError):
    """Raised when a file's text could not be extracted."""

    def __init__(self, mime_type: str, detail: str) -> None:
        super().__init__(
            f"Could not extract text from {mime_type}: {detail}",
            code="file_extraction_failed",
            status_code=422,
        )


class UnsupportedFileTypeError(AppError):
    """Raised when a MIME type has no registered extractor."""

    def __init__(self, mime_type: str) -> None:
        super().__init__(
            f"Unsupported file type: {mime_type}",
            code="unsupported_file_type",
            status_code=415,
        )


def extract_text(*, data: bytes, mime_type: str) -> str:
    """Extract plain text from ``data`` according to ``mime_type``.

    Returns possibly-empty text (an empty document is valid and simply yields
    zero chunks). Raises :class:`UnsupportedFileTypeError` for unknown types and
    :class:`ExtractionError` when a known parser fails.
    """
    if mime_type in _PLAINTEXT_MIME_TYPES:
        return _decode_text(data)
    if mime_type == "text/csv":
        return _extract_csv(data)
    if mime_type == "application/pdf":
        return _extract_pdf(data)
    if mime_type == (
        "application/vnd.openxmlformats-officedocument" ".wordprocessingml.document"
    ):
        return _extract_docx(data)
    if mime_type == (
        "application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet"
    ):
        return _extract_xlsx(data)
    raise UnsupportedFileTypeError(mime_type)


def _decode_text(data: bytes) -> str:
    """Decode bytes as UTF-8, replacing undecodable bytes (never raises)."""
    return data.decode("utf-8", errors="replace")


def _extract_csv(data: bytes) -> str:
    """Flatten CSV rows into newline-joined, comma-spaced text."""
    text = _decode_text(data)
    reader = csv.reader(io.StringIO(text))
    return "\n".join(", ".join(row) for row in reader)


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ExtractionError("application/pdf", "pypdf not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ExtractionError("application/pdf", str(exc)) from exc
    return "\n\n".join(pages).strip()


def _extract_docx(data: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ExtractionError(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document",
            "python-docx not installed",
        ) from exc
    try:
        document = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs]
    except Exception as exc:
        raise ExtractionError(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document",
            str(exc),
        ) from exc
    return "\n".join(paragraphs).strip()


def _extract_xlsx(data: bytes) -> str:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ExtractionError(
            "application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet",
            "openpyxl not installed",
        ) from exc
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
        lines: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    lines.append(", ".join(cells))
        workbook.close()
    except Exception as exc:
        raise ExtractionError(
            "application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet",
            str(exc),
        ) from exc
    return "\n".join(lines).strip()
