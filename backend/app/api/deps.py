"""Shared FastAPI dependencies.

Exposes the settings dependency and the request-scoped database session. The
authenticated ``current_user`` dependency lands with auth (Day 2+ of the plan).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.database.session import get_db

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
