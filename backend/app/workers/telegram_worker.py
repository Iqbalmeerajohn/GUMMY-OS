"""The Telegram worker — a phone client for a laptop-hosted assistant.

Polls Telegram for messages from allowlisted chats and runs each one as a
normal conversation turn: same orchestrator, same memory, same policy gate,
same audit trail. The transport is the only new thing, which is the point —
a second way in must not become a second, weaker way in.

Two decisions worth stating.

**One conversation per chat.** Each Telegram chat maps to a persistent
conversation, so context survives across messages and across restarts exactly
as it does in the browser. A new conversation per message would make Gummy
amnesiac on the device you use most.

**Messages are processed one at a time.** A local 3B model on a 4 GB card can
only generate one reply at a time anyway; accepting a second concurrently
would queue inside Ollama and make both slower while doubling memory
pressure. Serialising here keeps the failure mode legible.

Like the other workers, the loop outlives any single failure: one bad message
must not stop the transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.channels.telegram import (
    BACKOFF_SECONDS,
    IncomingMessage,
    TelegramClient,
    TelegramConfigError,
    extract_message,
    parse_allowed_chat_ids,
)

logger = logging.getLogger(__name__)

# Title used for the per-chat conversation, so it is recognisable in the UI.
CONVERSATION_TITLE = "Telegram"


class TelegramWorker:
    """Long-polls Telegram and runs each authorised message as a turn."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._client: TelegramClient | None = None
        self._token: str = ""
        self._allowed: frozenset[int] = frozenset()
        self._owner_user_id: uuid.UUID | None = None
        self._offset: int | None = None
        # chat_id -> conversation_id, rebuilt lazily after a restart.
        self._conversations: dict[int, uuid.UUID] = {}
        self.is_running = False
        self.messages_handled = 0

    def configure(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession] | None,
        token: str,
        allowed_chat_ids: str,
        owner_user_id: uuid.UUID | None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._token = token or ""
        self._allowed = parse_allowed_chat_ids(allowed_chat_ids)
        self._owner_user_id = owner_user_id

    def start(self) -> None:
        """Begin polling, or explain precisely why it stayed off."""
        if self._sessionmaker is None:
            logger.info("telegram worker idle (no database configured)")
            return
        if not self._token:
            logger.info("telegram worker idle (no bot token configured)")
            return
        if not self._allowed:
            # Deliberately a refusal, not a warning. A bot with no allowlist
            # answers anyone who finds it, using this user's memory and tools.
            logger.error(
                "telegram worker REFUSING to start: GUMMY_TELEGRAM_ALLOWED_CHAT_IDS "
                "is empty, which would let any Telegram user talk to your "
                "assistant. Set it to your own numeric chat id."
            )
            return
        if self._owner_user_id is None:
            logger.error(
                "telegram worker idle: GUMMY_TELEGRAM_OWNER_USER_ID is not set, "
                "so there is no account to attribute messages to."
            )
            return
        if self._task is not None and not self._task.done():
            return

        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info("telegram worker started (%d allowed chat(s))", len(self._allowed))

    async def stop(self) -> None:
        self.is_running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("telegram worker stopped")

    def status(self) -> dict[str, object]:
        return {
            "running": self.is_running,
            "allowed_chats": len(self._allowed),
            "messages_handled": self.messages_handled,
        }

    async def _run(self) -> None:
        try:
            self._client = TelegramClient(self._token)
        except TelegramConfigError:
            logger.exception("telegram worker could not start")
            self.is_running = False
            return

        while self.is_running:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # The transport must outlive a bad response or a dropped
                # connection; back off so a persistent fault does not spin.
                logger.exception("telegram poll failed; backing off")
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.sleep(BACKOFF_SECONDS)

    async def poll_once(self) -> int:
        """One long-poll cycle. Returns how many messages were handled.

        Separate from the loop so tests can drive it deterministically.
        """
        if self._client is None:
            return 0
        updates = await self._client.get_updates(self._offset)
        handled = 0
        for update in updates:
            # Advance past every update, including ones we filter out —
            # otherwise a message from an unlisted chat is re-fetched forever.
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = update_id + 1

            message = extract_message(update, self._allowed)
            if message is None:
                continue
            try:
                await self._handle(message)
                handled += 1
                self.messages_handled += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("failed to handle telegram message")
                with contextlib.suppress(Exception):
                    await self._client.send_message(
                        message.chat_id,
                        "Something went wrong handling that. It has been logged.",
                    )
        return handled

    async def _handle(self, message: IncomingMessage) -> None:
        """Run one message as a conversation turn and reply with the result."""
        assert self._client is not None
        assert self._sessionmaker is not None
        assert self._owner_user_id is not None

        await self._client.send_chat_action(message.chat_id)

        # Imported here rather than at module scope: the turn service pulls in
        # the whole agent stack, and a worker that may never start should not
        # add that to import time.
        from app.services.conversation import conversation_turn_service
        from app.services.embeddings.factory import get_embedding_service
        from app.services.llm.factory import get_llm_provider

        async with self._sessionmaker() as session:
            conversation_id = await self._conversation_for(session, message.chat_id)
            result = await conversation_turn_service.run_turn(
                session,
                user_id=self._owner_user_id,
                conversation_id=conversation_id,
                message=message.text,
                embedding_service=get_embedding_service(),
                llm=get_llm_provider(),
            )

        await self._client.send_message(message.chat_id, result.reply)

    async def _conversation_for(self, session: AsyncSession, chat_id: int) -> uuid.UUID:
        """The persistent conversation for one chat, created on first use."""
        cached = self._conversations.get(chat_id)
        if cached is not None:
            return cached

        from app.schemas.conversation import ConversationCreate
        from app.services.conversation import conversation_service

        conversation = await conversation_service.create_conversation(
            session,
            user_id=self._owner_user_id,  # type: ignore[arg-type]
            payload=ConversationCreate(title=f"{CONVERSATION_TITLE} {chat_id}"),
        )
        await session.commit()
        self._conversations[chat_id] = conversation.id
        return conversation.id


# Module-level singleton, started/stopped by the app lifespan.
telegram_worker = TelegramWorker()
