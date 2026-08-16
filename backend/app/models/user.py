"""User model — the tenancy root for the memory data model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.memory import Memory
    from app.models.user_profile import UserProfile


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An account; the parent of every memory record.

    Since 0022 this is also the credential store: GUMMY issues its own tokens,
    so password hashes and the Google subject id live here rather than in an
    external identity provider.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)

    # Null for accounts that only ever signed in with Google — distinguishable
    # from "has an unusable password", which a placeholder value would hide.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Google's stable `sub` claim — the join key for OAuth, because email can
    # change on the Google side while `sub` never does.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    memories: Mapped[list[Memory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
