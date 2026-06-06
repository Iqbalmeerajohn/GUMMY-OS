"""Shared FastAPI dependencies.

Exposes the settings dependency and the request-scoped database session. The
authenticated ``current_user`` dependency lands with auth (Day 2+ of the plan).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.factory import get_embedding_service

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]


async def get_current_user_id(
    user_id: Annotated[
        uuid.UUID,
        Query(description="Tenant user id. Temporary until auth lands."),
    ],
) -> uuid.UUID:
    """Resolve the acting tenant.

    Day 3 has no auth, so the tenant is passed explicitly as ``user_id``. This is
    the single seam that the authenticated ``current_user`` dependency replaces
    when auth ships — endpoints and services stay unchanged.
    """
    return user_id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
