"""Request-scoped tenant identity for Row-Level Security.

The authenticated user id is stashed in a ``ContextVar`` by ``get_current_user``
and read by the SQLAlchemy ``after_begin`` hook (in ``database.session``) to set
the Postgres GUC ``app.current_user_id`` on every transaction. This is how RLS
policies know the acting tenant. The value is cleared per request (in ``get_db``)
so it never leaks across requests on a keep-alive connection.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None
)


def set_current_user_id(user_id: uuid.UUID | None) -> None:
    """Set the acting tenant for the rest of the request."""
    _current_user_id.set(user_id)


def get_current_user_id() -> uuid.UUID | None:
    """Return the acting tenant, or None when unauthenticated/cleared."""
    return _current_user_id.get()
