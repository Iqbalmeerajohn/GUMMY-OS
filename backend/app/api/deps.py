"""Shared FastAPI dependencies.

Tenancy is resolved from a verified GUMMY JWT (`get_current_user`). The
``CurrentUserId`` alias keeps the **same name and type** it had under the legacy
query-parameter seam, so every endpoint and service is unchanged — only the
dependency behind it changed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.security import CurrentUser, verify_access_token
from app.core.tenant_context import set_current_user_id
from app.database.session import get_auth_sessionmaker, get_db
from app.repositories import user_repository
from app.services.auth import auth_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.factory import get_embedding_service
from app.services.llm.base import LLMProvider
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
AuthSessionmakerDep = Annotated[
    async_sessionmaker[AsyncSession] | None, Depends(get_auth_sessionmaker)
]


async def get_current_user(
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    user_id: Annotated[
        uuid.UUID | None,
        Query(description="Legacy/dev tenant id (replaced by the bearer token)."),
    ] = None,
) -> CurrentUser:
    """Resolve the acting tenant from a verified JWT (with a dev/legacy fallback).

    Order: (1) a bearer token is verified and the local user is upserted; (2) only
    if no token is present and ``auth_dev_bypass`` is on, the legacy ``user_id``
    query param (or a configured dev user) is accepted; (3) otherwise → 401.
    """
    if credentials is not None:
        claims = verify_access_token(credentials.credentials, settings)
        # Publish the tenant before any DB work so RLS (the per-transaction GUC)
        # applies to the user upsert itself.
        set_current_user_id(claims.sub)
        if sessionmaker is None:
            raise AppError(
                "Database is not configured.",
                code="database_unavailable",
                status_code=503,
            )
        async with sessionmaker() as session:
            user = await user_repository.upsert_user(
                session, user_id=claims.sub, email=claims.email
            )
            await session.commit()
        # Name comes from the verified JWT (user_metadata), not the DB, so
        # identity is available without a second read on the request path.
        return CurrentUser(id=user.id, email=user.email, display_name=claims.name)

    # Owner mode: a single-user local install runs without a login wall. Unlike
    # auth_dev_bypass this resolves a REAL persisted account, so anything Gummy
    # learns while running open stays owned by that account once sign-in is
    # enabled. Refused in production by assert_auth_safe.
    #
    # Gated on the owner being the ONLY account. Owner mode's whole premise is
    # "one person uses this machine", and that premise is checkable: the moment
    # a second account exists it is false, and answering an anonymous request
    # with the owner's identity stops being a convenience and becomes a data
    # leak — an unauthenticated caller was served the owner's memories and
    # conversations. It also silently defeats sign-out, because the client
    # discards its token, asks who it is, and is told it is still the owner.
    if settings.gummy_owner_mode:
        if sessionmaker is None:
            raise AppError(
                "Database is not configured.",
                code="database_unavailable",
                status_code=503,
            )
        async with sessionmaker() as session:
            if await user_repository.count_users(session) <= 1:
                owner = await auth_service.get_or_create_owner(
                    session, email=settings.gummy_owner_email
                )
                profile = CurrentUser(
                    id=owner.id, email=owner.email, display_name=owner.display_name
                )
                set_current_user_id(profile.id)
                return profile
        logger.warning(
            "owner mode is enabled but more than one account exists; "
            "refusing to auto-authenticate. Set GUMMY_OWNER_MODE=false."
        )

    if settings.auth_dev_bypass:
        if user_id is not None:
            set_current_user_id(user_id)
            return CurrentUser(id=user_id, email=None)
        if settings.auth_dev_user_id is not None:
            set_current_user_id(settings.auth_dev_user_id)
            return CurrentUser(id=settings.auth_dev_user_id, email=None)

    raise AppError("Authentication required.", code="missing_token", status_code=401)


async def _current_user_id(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> uuid.UUID:
    return user.id


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
CurrentUserId = Annotated[uuid.UUID, Depends(_current_user_id)]
