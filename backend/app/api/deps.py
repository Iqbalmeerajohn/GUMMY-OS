"""Shared FastAPI dependencies.

Day 1 exposes the settings dependency. The authenticated ``current_user`` and the
request-scoped database session land on Day 2 with auth and the ORM.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
