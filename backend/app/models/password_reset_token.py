"""PasswordResetToken model — single-use, short-lived password recovery.

Only the SHA-256 **hash** of the reset token is stored, mirroring
:mod:`app.models.refresh_token`. The raw token exists in exactly two places —
the delivered link and the request that redeems it — so a dump of this table
grants nobody a password reset.

A row is spent by stamping ``used_at`` rather than deleting it. Redemption then
distinguishes "never issued" from "already used", and the spent row remains as
evidence that the reset happened.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class PasswordResetToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One issued password-reset token, identified by its hash."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 64 hex chars of SHA-256. Unique so a hash collision or a double-insert is
    # a database error rather than an ambiguous lookup.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Stamped on successful redemption. Non-null means spent, and spent is
    # permanent — this is what makes a reset link single-use.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<PasswordResetToken id={self.id} user_id={self.user_id}>"
