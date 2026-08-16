"""Request/response schemas for the local auth endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# A deliberately permissive shape check rather than the full RFC 5322 grammar
# (which `EmailStr` brings a dependency for). Real address validity is proven by
# delivery, not by a regex, and this is the identity key for a local-first app —
# so the only job here is to reject obvious typos and non-addresses.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]

# Long enough to resist offline guessing, short enough not to annoy. The upper
# bound is not cosmetic: PBKDF2 hashes its input, so an unbounded password is a
# cheap way to make the server do unbounded work.
_PASSWORD = Field(min_length=8, max_length=128)


class SignUpRequest(BaseModel):
    email: Email
    password: str = _PASSWORD
    display_name: str | None = Field(default=None, max_length=255)


class SignInRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    """The authenticated account, as the client sees it."""

    id: uuid.UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    # When the account was created — the client renders "member since". Optional
    # because owner-mode and token-only responses resolve identity from claims
    # without necessarily loading the row.
    created_at: datetime | None = None


class SessionResponse(BaseModel):
    """A signed-in session: the credentials plus who they belong to."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class AuthConfigResponse(BaseModel):
    """What sign-in methods this server actually supports.

    Lets the client render only the buttons that will work, instead of showing
    a Google button that 503s because the server has no OAuth credentials.
    """

    password_enabled: bool = True
    google_enabled: bool
    owner_mode: bool
