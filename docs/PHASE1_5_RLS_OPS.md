# Phase 1.5 — RLS Operations (the `gummy_app` role)

> One-time operational steps for Row-Level Security. The Alembic migration
> `0005_enable_rls` enables RLS + policies; **role creation is a cluster privilege
> done out-of-band** (here), not in the migration.

> **Applied status:** `gummy_app` is **created and the runtime `DATABASE_URL` is
> switched to it** (connecting on the **direct** host, `:5432` — guaranteed role
> auth; the Supavisor pooler as `gummy_app.<ref>` is a later perf optimization).
> RLS is **actively enforced** through the app runtime (verified: tenant sees only
> its own rows; without the GUC, **zero** rows — i.e. no bypass). `DIRECT_DATABASE_URL`
> stays the owner connection for migrations. The previous URL is backed up at
> `backend/.env.bak`.

## Why a dedicated role

RLS policies are **not enforced for table owners or superusers** (they bypass RLS
unless `FORCE ROW LEVEL SECURITY`). Supabase's `postgres` / `service_role` therefore
bypass our policies — which is *useful during rollout* (the app keeps working on its
current connection while RLS is enabled), but means the app must eventually connect
as a **non-bypassing role** for isolation to actually apply.

`gummy_app` is that role: `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`.

## 1. Create the role (run once, in the Supabase SQL editor as a privileged role)

```sql
-- Pick a strong password and store it in your secret manager; never commit it.
CREATE ROLE gummy_app LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT USAGE ON SCHEMA public TO gummy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gummy_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gummy_app;

-- Future tables created by migrations inherit the grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gummy_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO gummy_app;
```

Notes:
- `gummy_app` can set the tenant GUC (`set_config('app.current_user_id', …, true)`)
  without extra privilege — `app.*` is a namespaced placeholder parameter.
- pgvector operators work via `USAGE ON SCHEMA public`.

## 2. Apply the schema migration

```bash
cd backend
uv run alembic upgrade head        # applies 0005_enable_rls
```

The app's current (`service_role`) connection **keeps working** because it bypasses
RLS. Nothing breaks at this step.

## 3. Switch the app connection to `gummy_app` (the enforcement step)

Point the runtime `DATABASE_URL` (and `DIRECT_DATABASE_URL` for migrations stays the
owner) at `gummy_app`:

```
DATABASE_URL=postgresql://gummy_app:<app_password>@<host>:5432/postgres
# DIRECT_DATABASE_URL stays the owner/service connection (migrations bypass RLS).
```

From here, every app query runs under RLS: the `after_begin` hook sets
`app.current_user_id` per transaction, and policies hide other tenants' rows. When
the GUC is unset, `current_setting('app.current_user_id', true)` is NULL → **fail
closed** (no rows).

## 4. Verify isolation

Run the gated integration test against the `gummy_app` connection:

```bash
RUN_RLS_PG_TESTS=1 RLS_TEST_DSN="postgresql+asyncpg://gummy_app:<pw>@<host>:5432/postgres" \
  uv run pytest tests/test_rls_postgres.py -v
```

It proves: a tenant sees only its own rows, cross-tenant `INSERT` fails the
`WITH CHECK`, and an unset GUC returns nothing.

## Rollback

```bash
uv run alembic downgrade -1        # drops policies + disables RLS + drops the column
# and revert DATABASE_URL to the service-role connection.
```
