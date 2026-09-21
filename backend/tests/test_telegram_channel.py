"""Telegram transport tests.

Almost all of the risk here is authorisation. A bot token addresses a globally
reachable endpoint, so "which chats may talk to this assistant" is the only
thing standing between a stranger and your memory. These tests assert that
boundary from both sides: the filter drops unlisted chats, and the worker
refuses to run at all without a list.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.channels.telegram import (
    TelegramClient,
    TelegramConfigError,
    extract_message,
    parse_allowed_chat_ids,
)
from app.workers.telegram_worker import TelegramWorker

ALLOWED = frozenset({12345})


def _update(chat_id: int, text: str = "hello", *, update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 7,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"username": "someone"},
            "text": text,
        },
    }


# ── allowlist parsing ────────────────────────────────────────────────────────


def test_empty_allowlist_parses_to_nothing() -> None:
    assert parse_allowed_chat_ids(None) == frozenset()
    assert parse_allowed_chat_ids("") == frozenset()
    assert parse_allowed_chat_ids("  ,  ") == frozenset()


def test_allowlist_parses_multiple_ids() -> None:
    assert parse_allowed_chat_ids(" 1, 2 ,3 ") == frozenset({1, 2, 3})


def test_allowlist_ignores_junk_without_failing_open() -> None:
    """A typo drops that entry; it must never widen the allowlist."""
    assert parse_allowed_chat_ids("12345,notanid") == frozenset({12345})


def test_allowlist_handles_negative_group_ids() -> None:
    """Telegram group chat ids are negative."""
    assert parse_allowed_chat_ids("-1001234567890") == frozenset({-1001234567890})


# ── message filtering ────────────────────────────────────────────────────────


def test_allowed_chat_yields_a_message() -> None:
    message = extract_message(_update(12345, "ping"), ALLOWED)
    assert message is not None
    assert message.chat_id == 12345
    assert message.text == "ping"


def test_unlisted_chat_is_dropped() -> None:
    """The single most important assertion in this file."""
    assert extract_message(_update(99999, "let me in"), ALLOWED) is None


def test_no_allowlist_means_nobody(caplog: pytest.LogCaptureFixture) -> None:
    assert extract_message(_update(12345), frozenset()) is None


def test_non_message_updates_are_ignored() -> None:
    assert extract_message({"update_id": 1}, ALLOWED) is None
    assert extract_message({"update_id": 1, "poll": {}}, ALLOWED) is None


def test_non_text_messages_are_ignored() -> None:
    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 12345}, "photo": [{}]},
    }
    assert extract_message(update, ALLOWED) is None


def test_blank_text_is_ignored() -> None:
    assert extract_message(_update(12345, "   "), ALLOWED) is None


def test_edited_messages_are_handled() -> None:
    update = {
        "update_id": 2,
        "edited_message": {
            "message_id": 7,
            "chat": {"id": 12345},
            "from": {"username": "u"},
            "text": "fixed typo",
        },
    }
    message = extract_message(update, ALLOWED)
    assert message is not None and message.text == "fixed typo"


def test_text_is_stripped() -> None:
    message = extract_message(_update(12345, "  spaced  "), ALLOWED)
    assert message is not None and message.text == "spaced"


# ── client construction ──────────────────────────────────────────────────────


async def test_client_requires_a_token() -> None:
    with pytest.raises(TelegramConfigError, match="bot token is required"):
        TelegramClient("")


async def test_client_builds_its_base_url() -> None:
    client = TelegramClient("abc123", api_root="https://example.test")
    try:
        assert client._base == "https://example.test/botabc123"
    finally:
        await client.aclose()


# ── worker refusal paths ─────────────────────────────────────────────────────


def _worker(**overrides) -> TelegramWorker:
    worker = TelegramWorker()
    config = {
        "sessionmaker": object(),  # only presence is checked before starting
        "token": "token",
        "allowed_chat_ids": "12345",
        "owner_user_id": uuid.uuid4(),
    }
    config.update(overrides)
    worker.configure(**config)  # type: ignore[arg-type]
    return worker


def test_worker_refuses_to_start_without_an_allowlist(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty allowlist is a misconfiguration, never 'allow everyone'."""
    worker = _worker(allowed_chat_ids="")
    with caplog.at_level("ERROR"):
        worker.start()
    assert worker.is_running is False
    assert "REFUSING to start" in caplog.text


def test_worker_stays_off_without_a_token() -> None:
    worker = _worker(token="")
    worker.start()
    assert worker.is_running is False


def test_worker_stays_off_without_an_owner() -> None:
    worker = _worker(owner_user_id=None)
    worker.start()
    assert worker.is_running is False


def test_worker_stays_off_without_a_database() -> None:
    worker = _worker(sessionmaker=None)
    worker.start()
    assert worker.is_running is False


def test_status_reports_configuration() -> None:
    worker = _worker()
    status = worker.status()
    assert status["running"] is False
    assert status["allowed_chats"] == 1
    assert status["messages_handled"] == 0


# ── offset handling ──────────────────────────────────────────────────────────


async def test_offset_advances_past_filtered_updates() -> None:
    """A message from an unlisted chat must not be re-fetched forever.

    If the offset only advanced for handled messages, one unlisted sender
    would wedge the poll loop on the same update permanently.
    """
    worker = _worker()

    class _FakeClient:
        def __init__(self) -> None:
            self.sent: list[tuple[int, str]] = []

        async def get_updates(self, offset: int | None) -> list[dict]:
            return [_update(99999, "not allowed", update_id=41)]

        async def send_message(self, chat_id: int, text: str) -> None:
            self.sent.append((chat_id, text))

        async def send_chat_action(self, chat_id: int) -> None:
            pass

    worker._client = _FakeClient()  # type: ignore[assignment]
    handled = await worker.poll_once()

    assert handled == 0
    assert worker._offset == 42
