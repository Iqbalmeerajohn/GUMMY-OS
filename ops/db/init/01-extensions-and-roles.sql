-- GUMMY OS — local database bootstrap.
--
-- Runs ONCE, as the superuser, when the data volume is first created. It
-- reproduces locally what docs/PHASE1_5_RLS_OPS.md sets up by hand in Supabase,
-- so Row-Level Security is genuinely enforced in local development instead of
-- being silently bypassed.
--
-- Two roles, deliberately:
--   gummy      — owner/superuser. Runs migrations (DIRECT_DATABASE_URL).
--                Owners BYPASS RLS, which is exactly what DDL needs.
--   gummy_app  — the runtime role (DATABASE_URL). NOSUPERUSER + NOBYPASSRLS, so
--                every app query is subject to the tenant policies. Without this
--                split, local dev would bypass RLS and tenant-isolation bugs
--                would only ever appear in production.

-- pgvector: required by memory_embeddings / conversation_summary_embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram index support for the keyword/lexical half of hybrid retrieval.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── The non-bypassing application role ──────────────────────────────────────
-- Password is a local-development constant by design; it never leaves this
-- machine and the port is bound to localhost. Production uses a secret manager.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN
    CREATE ROLE gummy_app LOGIN PASSWORD 'gummy_local_dev'
      NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO gummy_app;

-- Existing objects (none on a fresh volume, but keeps this script re-runnable).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gummy_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gummy_app;

-- Tables created LATER by Alembic (running as `gummy`) inherit these grants.
-- FOR ROLE gummy is essential: default privileges attach to the creating role,
-- so omitting it would leave every migrated table unreadable by gummy_app.
ALTER DEFAULT PRIVILEGES FOR ROLE gummy IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gummy_app;
ALTER DEFAULT PRIVILEGES FOR ROLE gummy IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO gummy_app;
