"""Whether the app thinks it is behind a transaction pooler.

This one boolean decides whether asyncpg's prepared-statement caches are turned
off. Behind a pooler that is a correctness requirement: consecutive
transactions land on different physical backends, and a statement prepared on
one is missing on the next, which broke the per-transaction RLS `set_config`
call. Without a pooler it is an expensive mistake — every statement is prepared
and discarded, and `pool_pre_ping` issues one on every checkout, which measured
at 48.5 ms per request against a direct local Postgres versus 3.5 ms with
caching left on.

Both directions are therefore worth pinning: guessing "pooler" costs ~45 ms on
every API call, and guessing "direct" reintroduces a bug that took real effort
to diagnose.
"""

from __future__ import annotations

from app.core.config import Settings


def _settings(url: str | None, **kw: object) -> Settings:
    return Settings(database_url=url, **kw)  # type: ignore[arg-type]


def test_direct_local_postgres_is_not_a_pooler() -> None:
    """The local-first default. Anything else here is pure added latency."""
    url = "postgresql+asyncpg://u:p@localhost:5432/gummy"
    assert _settings(url).uses_transaction_pooler is False


def test_supabase_pooler_port_is_detected() -> None:
    url = "postgresql://u:p@db.example.supabase.com:6543/postgres"
    assert _settings(url).uses_transaction_pooler is True


def test_pgbouncer_default_port_is_detected() -> None:
    assert _settings("postgresql://u:p@host:6432/db").uses_transaction_pooler is True


def test_pooler_hostname_is_detected() -> None:
    url = "postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    assert _settings(url).uses_transaction_pooler is True


def test_pgbouncer_in_the_url_is_detected() -> None:
    url = "postgresql://u:p@host:5432/db?pgbouncer=true"
    assert _settings(url).uses_transaction_pooler is True


def test_explicit_configuration_overrides_the_heuristic() -> None:
    """A pooler the heuristic cannot recognise must still be configurable."""
    direct = "postgresql://u:p@localhost:5432/gummy"
    assert _settings(direct, db_transaction_pooler=True).uses_transaction_pooler is True

    pooled = "postgresql://u:p@host:6543/db"
    forced = _settings(pooled, db_transaction_pooler=False)
    assert forced.uses_transaction_pooler is False


def test_no_database_url_is_not_a_pooler() -> None:
    assert _settings(None).uses_transaction_pooler is False


def test_connect_args_are_empty_for_a_direct_connection() -> None:
    """The 45 ms regression would show up here first."""
    from app.database import session as db_session

    settings = _settings("postgresql+asyncpg://u:p@localhost:5432/gummy")
    original = db_session.get_settings
    db_session.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        assert db_session._connect_args() == {}
    finally:
        db_session.get_settings = original  # type: ignore[assignment]


def test_connect_args_disable_statement_caching_behind_a_pooler() -> None:
    from app.database import session as db_session

    settings = _settings("postgresql://u:p@host:6543/db")
    original = db_session.get_settings
    db_session.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        args = db_session._connect_args()
        assert args["statement_cache_size"] == 0
        assert args["prepared_statement_cache_size"] == 0
        # Unique names, or a name prepared on one backend collides on the next.
        assert (
            args["prepared_statement_name_func"]()
            != args["prepared_statement_name_func"]()
        )
    finally:
        db_session.get_settings = original  # type: ignore[assignment]
