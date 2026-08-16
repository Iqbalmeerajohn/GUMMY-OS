"""Connector endpoints (``/api/v1/connectors``) — import the user's own data.

Thin HTTP layer over the connector services. Every import is explicit: the user
supplies the source, the data lands in their local database, and nothing is
scheduled or sent anywhere.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserId, DbSession
from app.services.connectors import google_calendar

router = APIRouter(prefix="/connectors", tags=["connectors"])


class CalendarImportRequest(BaseModel):
    """A calendar to import: a secret iCal URL, or a pasted ``.ics`` document."""

    ics_url: str | None = Field(default=None, max_length=2048)
    ics_text: str | None = Field(default=None, max_length=5_000_000)


class ImportResponse(BaseModel):
    """What an import actually stored."""

    imported: int
    # The first few, so the client can show what landed rather than a bare count.
    preview: list[str]


@router.post("/calendar", response_model=ImportResponse)
async def import_calendar(
    body: CalendarImportRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> ImportResponse:
    """Import past events from a calendar feed or an ``.ics`` file.

    Re-importing is safe: consolidation reinforces facts it already holds rather
    than storing them twice, so a user can point this at the same calendar every
    week without their memory filling up with copies.
    """
    if body.ics_text:
        memories = await google_calendar.import_from_text(
            session, user_id=user_id, text=body.ics_text
        )
    elif body.ics_url:
        memories = await google_calendar.import_from_url(
            session, user_id=user_id, url=body.ics_url
        )
    else:
        memories = []
    return ImportResponse(
        imported=len(memories),
        preview=[m.content for m in memories[:5]],
    )
