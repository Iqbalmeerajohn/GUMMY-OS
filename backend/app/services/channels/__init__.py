"""Message transports that reach Gummy from somewhere other than the browser.

A transport only carries text. Everything it delivers runs through the same
conversation turn, the same memory, and the same policy gate as a message
typed into the web UI — a second way in must not be a weaker way in.
"""

from app.services.channels.telegram import (
    IncomingMessage,
    TelegramClient,
    TelegramConfigError,
    extract_message,
    parse_allowed_chat_ids,
)

__all__ = [
    "IncomingMessage",
    "TelegramClient",
    "TelegramConfigError",
    "extract_message",
    "parse_allowed_chat_ids",
]
