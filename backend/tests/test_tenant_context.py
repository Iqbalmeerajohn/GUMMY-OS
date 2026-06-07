"""Tenant-context (RLS GUC source) unit tests."""

from __future__ import annotations

import uuid

from app.core.tenant_context import get_current_user_id, set_current_user_id


def test_defaults_to_none() -> None:
    set_current_user_id(None)
    assert get_current_user_id() is None


def test_set_and_get() -> None:
    uid = uuid.uuid4()
    set_current_user_id(uid)
    try:
        assert get_current_user_id() == uid
    finally:
        set_current_user_id(None)
