"""Telegram transport — Gummy, reachable from a phone.

A local-first assistant that only exists on the machine it runs on is a
workstation tool, not a personal one. The gap this closes is mobility: the
model, the memory and the database stay on your hardware, and only the
conversation crosses the network.

**Long polling, not webhooks.** Telegram can push updates to a public HTTPS
endpoint, which would mean exposing this backend to the internet. Polling
means the machine only ever makes *outbound* connections, so the whole system
stays reachable from a phone without opening a single inbound port. That is
the right trade for something whose premise is that it runs at home.

**The allowlist is not optional.** A bot token is a bearer credential for a
globally addressable endpoint: anyone who learns the bot's handle can message
it. Without ``allowed_chat_ids`` this worker refuses to start rather than
serving a stranger's messages with your memory and your tools. An empty
allowlist is a misconfiguration, not "allow everyone".

Message text is untrusted input in the ordinary way — it becomes a user turn,
and every tool it might reach is still behind the policy gate.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
# Telegram holds the request open until an update arrives or this elapses, so
# a long value means near-instant delivery with almost no request volume.
LONG_POLL_SECONDS = 25
# Telegram rejects messages above 4096 characters outright.
MAX_MESSAGE_CHARS = 4000
# How long to wait before retrying after a transport error, so a network blip
# does not become a tight loop against Telegram's API.
BACKOFF_SECONDS = 5.0


class TelegramConfigError(ValueError):
    """The bot is misconfigured in a way that must not be started."""


@dataclass(frozen=True)
class IncomingMessage:
    """One inbound message, already authorised against the allowlist."""

    chat_id: int
    text: str
    message_id: int
    sender: str


def parse_allowed_chat_ids(raw: str | None) -> frozenset[int]:
    """Parse the comma-separated allowlist. Non-numeric entries are dropped."""
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            ids.add(int(candidate))
        except ValueError:
            logger.warning("ignoring non-numeric telegram chat id %r", candidate)
    return frozenset(ids)


class TelegramClient:
    """Thin wrapper over the Bot API calls this worker needs."""

    def __init__(self, token: str, *, api_root: str = API_ROOT) -> None:
        if not token:
            raise TelegramConfigError("a bot token is required")
        self._base = f"{api_root}/bot{token}"
        # Slightly longer than the long-poll window so the client does not
        # time out the request Telegram is deliberately holding open.
        self._http = httpx.AsyncClient(timeout=LONG_POLL_SECONDS + 10)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_updates(self, offset: int | None) -> list[dict]:
        params: dict[str, int] = {"timeout": LONG_POLL_SECONDS}
        if offset is not None:
            params["offset"] = offset
        response = await self._http.get(f"{self._base}/getUpdates", params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("description", "getUpdates failed")))
        return payload.get("result", []) or []

    async def send_message(self, chat_id: int, text: str) -> None:
        """Send one reply, chunked to Telegram's length limit."""
        body = text or "(no response)"
        for start in range(0, len(body), MAX_MESSAGE_CHARS):
            chunk = body[start : start + MAX_MESSAGE_CHARS]
            response = await self._http.post(
                f"{self._base}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
            )
            response.raise_for_status()

    async def send_chat_action(self, chat_id: int) -> None:
        """Show 'typing…'. Best-effort: a local model can take 20s, and
        silence for 20s reads as broken."""
        with contextlib.suppress(httpx.HTTPError):
            await self._http.post(
                f"{self._base}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )


def extract_message(update: dict, allowed: frozenset[int]) -> IncomingMessage | None:
    """Pull an authorised text message out of one update, or return None.

    Everything is filtered here: non-message updates, edits, non-text content,
    and — the important one — any chat that is not on the allowlist.
    """
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or chat_id not in allowed:
        if isinstance(chat_id, int):
            logger.warning("ignoring telegram message from unlisted chat %d", chat_id)
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    sender = (message.get("from") or {}).get("username") or str(chat_id)
    return IncomingMessage(
        chat_id=chat_id,
        text=text.strip(),
        message_id=int(message.get("message_id", 0)),
        sender=str(sender),
    )
