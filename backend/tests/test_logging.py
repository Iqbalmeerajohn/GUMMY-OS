"""JsonFormatter tests — structured ``extra=`` fields reach the JSON line.

The turn-timing instrumentation relies on the formatter surfacing arbitrary
``extra`` fields (e.g. ``total_turn_ms``) as top-level keys, not swallowing them.
"""

from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="turn_timing",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_core_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["message"] == "turn_timing"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert "timestamp" in payload


def test_formatter_merges_extra_structured_fields() -> None:
    payload = json.loads(
        JsonFormatter().format(
            _record(total_turn_ms=123.4, first_token_ms=42.0, event="turn_timing")
        )
    )
    assert payload["total_turn_ms"] == 123.4
    assert payload["first_token_ms"] == 42.0
    assert payload["event"] == "turn_timing"


def test_formatter_does_not_leak_reserved_attrs() -> None:
    payload = json.loads(JsonFormatter().format(_record()))
    # Internal LogRecord bookkeeping must not bleed into the structured line.
    for reserved in ("args", "msg", "levelno", "pathname"):
        assert reserved not in payload
