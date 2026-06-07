# GUMMY OS — Phase 1.5 Plan: Authentication + Row-Level Security

> Security-hardening phase between the verified Phase 1 Memory Engine and the
> Phase 2 Conversation System. Replaces the spoofable `user_id` query-parameter
> tenancy seam with **verified identity (JWT)** and **database-enforced isolation
> (RLS)** — so every future table is born tenant-safe.

> **Status:** Planning / design for review. **No implementation yet.**
> **Companion docs:** [PHASE1_PROGRESS.md](PHASE1_PROGRESS.md),
> [PHASE1_VERIFICATION.md](PHASE1_VERIFICATION.md),
> [../architecture/security-system.md](../architecture/security-system.md).

---

## 1. Objective & Rationale

Phase 1 is production-verified as an *engine*, but tenancy is currently an explicit
`user_id` **query parameter** ([deps.py](../backend/app/api/deps.py)
`get_current_user_id`) — trivially spoofable, with isolation enforced only in
application code. Two facts make hardening the right next step, *before* feature
work:

1. **RLS depends on trustworthy identity.** Postgres RLS enforces policies against
   an authenticated principal. Enforcing it against a client-supplied parameter is
   meaningless — so **Auth is a hard prerequisite for RLS**.
2. **Privacy is the product.** GUMMY's value proposition is *private, consent-based
   memory*. The Phase 2 Conversation System's core job is the memory-capture loop —
   scaling the amount of private data captured. Doing that before isolation is
   backwards.

The `user_id` seam was deliberately built to be swapped for auth with **zero
endpoint/service changes**; this is the cheapest moment to do it, before more
surface depends on the placeholder.

---

## 2. Scope — Two Increments

Phase 1.5 is split into two reviewable increments. **Increment A is detailed in
§3** (the deliverable for this review). Increment B is summarized in §4; its full
design lands in a follow-up doc.

| Increment | Delivers | Migration |
| --- | --- | --- |
| **A — JWT Authentication** | Verified identity replaces the `user_id` param; `CurrentUser` dependency; Supabase JWT verification; dev/test bypass. | **None (schema-free).** |
| **B — Row-Level Security** | DB-enforced tenant isolation; dedicated app DB role; per-transaction tenant GUC; RLS policies on all tables. | **`0005_enable_rls`** (+ `memory_embeddings.user_id`). |

### Roadmap item → increment mapping

| Roadmap item (from the recommendation) | Increment |
| --- | --- |
| Supabase Auth | A |
| JWT verification | A |
| `CurrentUser` dependency replacement | A |
| Session tenant context (GUC) | B |
| PostgreSQL Row-Level Security | B |
| Alembic migration `0005` | B |
| Integration testing strategy | A (auth unit) + B (RLS integration) |
| Rollout plan | A & B (each phased + reversible) |

> **Sequencing:** Ship **A** first behind a flag (non-breaking), confirm in
> staging, then ship **B** (which consumes A's verified identity). B is never
> shipped before A.

---

## 3. Increment A — JWT Authentication (Detailed Design)

### 3.1 Goal

Resolve the acting tenant from a **verified Supabase JWT** instead of a query
parameter, while keeping a **flag-gated legacy/dev path** so the existing test
suite and local workflows keep working during the transition. **Every endpoint and
service stays unchanged** — only the dependency behind `CurrentUserId` changes.

### 3.2 Supabase Auth integration

- **Who issues tokens:** the frontend (supabase-js `signInWith…`) obtains a session
  whose `access_token` is a JWT. (Frontend is a Phase 1+ placeholder; until it
  exists, tokens are minted in tests or obtained via Supabase REST for manual
  checks.)
- **How the backend verifies:** **statelessly** — it validates the JWT signature and
  claims locally; it does **not** call Supabase per request (no added latency or
  coupling). An optional `GET {SUPABASE_URL}/auth/v1/user` call is explicitly *not*
  used.
- **Claims relied upon:**

  | Claim | Use |
  | --- | --- |
  | `sub` | Supabase user UUID → becomes `users.id` (see §3.6). |
  | `email` | Stored on the local `users` row. |
  | `aud` | Must equal `authenticated` (reject otherwise). |
  | `exp` / `iat` | Expiry (with small leeway); reject expired. |
  | `iss` | Optionally pinned to `{SUPABASE_URL}/auth/v1`. |

- **Signing schemes (config-gated):**
  - **Primary — HS256 (symmetric):** verify with `SUPABASE_JWT_SECRET` (already in
    [config.py](../backend/app/core/config.py)). This is the default.
  - **Future — asymmetric (ES256/RS256) via JWKS:** newer Supabase projects sign
    with rotating keys exposed at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
    (header carries `kid`). The design leaves a config switch
    (`SUPABASE_JWT_ALGORITHMS`) and a cached-JWKS verification path; implementation
    of JWKS is deferred unless the project enables asymmetric keys.

### 3.3 JWT verification architecture

A small, pure verification module with no DB/HTTP coupling:

```text
core/security.py  (design sketch — not final code)
──────────────────────────────────────────────────
@dataclass(frozen=True)
class TokenClaims:
    sub: uuid.UUID
    email: str | None
    raw: dict

class AuthError(AppError):          # 401 envelope, codes below
    ...

def verify_access_token(token: str, settings) -> TokenClaims:
    # jwt.decode(token, key=settings.supabase_jwt_secret,
    #            algorithms=settings.supabase_jwt_algorithms,
    #            audience=settings.supabase_jwt_aud,
    #            options={"require": ["exp", "sub"]}, leeway=30)
    # map jwt exceptions -> AuthError(401):
    #   ExpiredSignatureError       -> code="token_expired"
    #   InvalidAudienceError/...    -> code="invalid_token"
    #   DecodeError/InvalidToken    -> code="invalid_token"
    # parse sub -> uuid.UUID; return TokenClaims(...)
```

- **Library:** `pyjwt[crypto]` (the `crypto` extra is harmless for HS256 and ready
  for ES/RS later).
- **Error mapping:** all failures → `AppError(status_code=401, code=…)` so the API
  returns the standard `{"error": {...}}` envelope (never FastAPI's default 403).

### 3.4 Exact request flow

```
1. Client logs in via supabase-js  ──►  access_token (JWT)
2. Client request:
       POST /api/v1/chat
       Authorization: Bearer <access_token>
3. FastAPI resolves dependency get_current_user(...):
   a. bearer = HTTPBearer(auto_error=False) extracts the token (or None)
   b. if bearer present:
          claims = verify_access_token(bearer, settings)      # signature/exp/aud
          user   = upsert_user(id=claims.sub, email=claims.email)
          return CurrentUser(id=user.id, email=user.email)
   c. elif settings.auth_dev_bypass and user_id query param present:   # LEGACY/DEV
          user = ensure_user(user_id)                                  # flag-gated
          return CurrentUser(id=user_id, email=None)
   d. elif settings.auth_dev_bypass and settings.auth_dev_user_id:     # DEV default
          return CurrentUser(id=auth_dev_user_id, ...)
   e. else:
          raise AppError(401, "missing_token")
4. CurrentUserId (= CurrentUser.id) flows into the endpoint unchanged.
5. Endpoint/service run exactly as today, scoped by user_id.
```

- The **dev/legacy paths (c, d)** are **off by default** and exist only to make the
  cutover non-breaking (existing tests pass `user_id`; see §3.7). Production runs
  with `auth_dev_bypass=false` → **token required**.
- **Startup guard:** if `app_env == "production"` and `auth_dev_bypass` is true, the
  app **fails to start** (fatal config error) — bypass can never ship to prod.

### 3.5 Dependency-injection changes

The seam is preserved by keeping the **same alias name and type**:

```text
api/deps.py  (design sketch)
────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)   # adds the Authorize button in /docs

async def get_current_user(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    user_id: Annotated[uuid.UUID | None, Query(description="Legacy/dev only")] = None,
) -> CurrentUser: ...

async def _current_user_id(user: CurrentUser = Depends(get_current_user)) -> uuid.UUID:
    return user.id

CurrentUser    = Annotated[CurrentUserModel, Depends(get_current_user)]   # NEW (rich: id+email)
CurrentUserId  = Annotated[uuid.UUID,        Depends(_current_user_id)]   # SAME name/type as today
```

- Endpoints keep `user_id: CurrentUserId` → **no endpoint or service edits**.
- `get_current_user` performs the **user upsert** using its own short-lived session
  (via `get_sessionmaker`) — independent of the request `DbSession`. This keeps
  Increment A decoupled and establishes the "resolve user before the request
  session" ordering that Increment B's tenant-GUC will rely on.
- Because the dependency still *declares* a `user_id` query param (legacy path), the
  OpenAPI schema keeps it during the transition; it is removed in the final rollout
  step.

### 3.6 Identity model & user upsert

- **Decision: `users.id` = Supabase `sub`.** On first authenticated request,
  `upsert_user(id=sub, email)` inserts a `users` row keyed by the Supabase UUID;
  thereafter it fetches (and may refresh `email`). This keeps the existing FK chain
  (`memories.user_id → users.id`) and — critically for Increment B — makes the RLS
  tenant key, the JWT `sub`, and `users.id` **one identity**.
- The current `users` model ([user.py](../backend/app/models/user.py)) is `id, email,
  created_at, updated_at`. The `id` column already has a server default
  (`gen_random_uuid()`); the upsert simply **supplies `id` explicitly**, so no
  schema change is needed.
- **Edge — legacy rows:** pre-auth rows (e.g. the `acf525e0…` verification user,
  created with a random UUID) won't match any Supabase `sub`. They are **dev-only**
  and reconciled in rollout (§3.10). New authenticated users are always keyed by
  `sub`.
- **Edge — email collision:** if a `sub`-keyed insert hits the `uq_users_email`
  constraint (an existing row with that email but a different id), the upsert
  **logs and reconciles** rather than crashing. In production, emails are fresh; in
  dev, this only affects the legacy rows above.

### 3.7 Test strategy

**Goal: keep all 87 existing tests green, add focused auth tests, stay hermetic
(no network).**

- **Keep existing API tests passing** by running the suite with
  `AUTH_DEV_BYPASS=true` (set in the hermetic env block of
  [conftest.py](../backend/tests/conftest.py), alongside the existing
  `DATABASE_URL=""`). The legacy `params={"user_id": …}` path (§3.4c) then satisfies
  `CurrentUserId` exactly as today — **no changes to existing test files**.
- **New `tests/test_auth.py` (unit, hermetic):** mint tokens with PyJWT using a
  test `SUPABASE_JWT_SECRET`, and assert:

  | Case | Expected |
  | --- | --- |
  | Valid HS256 token | `200`; `CurrentUser.id == sub`; user row upserted |
  | Expired token (`exp` past) | `401 token_expired` |
  | Bad signature (wrong secret) | `401 invalid_token` |
  | Wrong `aud` | `401 invalid_token` |
  | Malformed / non-JWT bearer | `401 invalid_token` |
  | No token, bypass **off** | `401 missing_token` |
  | No token, bypass **on**, `user_id` param | `200` (legacy path) |

- **Dependency override:** `api_client` can additionally override `get_current_user`
  to a fixed test user where a test wants to assert token-independent behavior
  (same pattern as the existing `get_db`/embedding/LLM overrides).
- **Production-guard test:** `app_env=production` + `auth_dev_bypass=true` → app
  construction raises (fatal).
- **Integration (manual / optional):** verify a *real* Supabase-issued token against
  the live project — kept out of the fast suite (mirrors how pgvector/Claude are
  validated live, not in unit tests).

### 3.8 Migration impact

- **None.** Increment A is **schema-free**: `users.id = sub` is achieved by
  supplying the id on upsert against the existing column; no new columns, no Alembic
  revision.
- *Optional, deferred:* a `last_login_at` column for login tracking — if wanted,
  it folds into Increment B's `0005` migration rather than adding a revision here.
- The Alembic chain therefore stays `0001 → 0004` through Increment A; `0005`
  belongs to Increment B (RLS).

### 3.9 Risks & mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Dev bypass reaches production** (auth disabled) | Critical | Default `auth_dev_bypass=false`; **startup guard** fails the app if bypass is on in `production`; covered by a test. |
| **HS256 secret leak → forgeable tokens** | High | Keep `SUPABASE_JWT_SECRET` server-side only; plan migration to asymmetric (JWKS) where the backend holds only a public key. |
| **Tokens from a different project / wrong audience** | High | Validate `aud == authenticated` (and optionally pin `iss` to the project URL). |
| **Supabase switched to asymmetric signing keys** | Medium | `SUPABASE_JWT_ALGORITHMS` config switch + planned JWKS path; HS256 failures surface clearly as `401 invalid_token`. |
| **Clock skew rejects valid tokens** | Low | 30s `leeway` on `exp`/`iat`. |
| **Email-unique collision on upsert** | Low | Reconcile-and-log upsert; prod emails are fresh; only legacy dev rows affected. |
| **Breaking existing clients/tests at cutover** | Medium | Flag-gated legacy `user_id` path during transition; removed only in the final rollout step. |
| **No blast radius beyond 401** | — | RLS isn't in yet, so auth alone can only *reject* requests — never leak or lose data. |

### 3.10 Rollout strategy (phased & reversible)

1. **Ship A behind flags** (`AUTH_ENABLED`, `AUTH_DEV_BYPASS`, `AUTH_DEV_USER_ID`) —
   non-breaking: legacy `user_id` path stays active in dev/test.
2. **Wire the frontend** (supabase-js) to send `Authorization: Bearer …`; until then,
   exercise the token path with minted/real tokens.
3. **Identity reconciliation:** new users → `id=sub`; quarantine/annotate pre-auth
   dev rows.
4. **Flip production to enforce** (`auth_dev_bypass=false`) — token now required.
5. **Remove the legacy `user_id` param** from the dependency once the frontend is
   fully on tokens.

**Rollback:** because A is flag-gated and **schema-free**, rollback is a **config
toggle** (re-enable `auth_dev_bypass`) — no migration to reverse, no data risk. A
code-level revert simply re-points `CurrentUserId` at the old query-param
dependency (preserved in git history). Worst-case production symptom is `401`s, not
data exposure.

### 3.11 Files to create / modify (Increment A)

| File | Action | Purpose |
| --- | --- | --- |
| `app/core/security.py` | **create** | `TokenClaims`, `AuthError`, `verify_access_token`. |
| `app/api/deps.py` | modify | Replace `get_current_user_id` with `get_current_user` + `_current_user_id`; keep `CurrentUserId`; add `CurrentUser`. |
| `app/core/config.py` | modify | Add `auth_enabled`, `auth_dev_bypass`, `auth_dev_user_id`, `supabase_jwt_aud` (default `authenticated`), `supabase_jwt_algorithms` (default `["HS256"]`); production startup guard. |
| `app/services/user/user_service.py` *(or repo helper)* | **create** | `upsert_user(id, email)` (idempotent, email-collision-safe). |
| `app/main.py` | modify | Production-guard assertion at startup (bypass off in prod). |
| `pyproject.toml`, `requirements.txt` | modify | Add `pyjwt[crypto]`. |
| `.env.example` | modify | Document `AUTH_ENABLED`, `AUTH_DEV_BYPASS`, `AUTH_DEV_USER_ID`, `SUPABASE_JWT_AUD`. |
| `tests/conftest.py` | modify | Set `AUTH_DEV_BYPASS=true` in the hermetic env block; optional `get_current_user` override. |
| `tests/test_auth.py` | **create** | Token verification + dependency + production-guard tests. |

> **Unchanged:** every endpoint in `app/api/v1/*` and every service — the seam holds.

---

## 4. Increment B — Row-Level Security (Summary)

*(Detailed design to follow in its own document; summarized here for context.)*

- **Dedicated app DB role** (`gummy_app`, `NOBYPASSRLS`) for the app connection;
  migrations keep using the owner/service connection.
- **Per-transaction tenant GUC** — set `SET LOCAL app.current_user_id = <id>` on
  **every** transaction via a SQLAlchemy `after_begin` hook reading a request
  `ContextVar` (set by `get_current_user`). Required because Supabase's transaction
  pooler doesn't carry session-level `SET` across transactions, and services commit
  multiple times per request.
- **`memory_embeddings.user_id`** added (backfilled) so its RLS policy is a simple
  column check, consistent with the other tables.
- **RLS policies** on `users`, `memories`, `memory_versions`, `memory_embeddings`:
  `USING (user_id = current_setting('app.current_user_id', true)::uuid)` (+
  `WITH CHECK`). `current_setting(..., true)` → **fails closed** when unset.
- **Migration `0005_enable_rls`**; **role creation** is a one-time Supabase SQL ops
  step (cluster privilege), not in the migration.
- **Testing:** unit suite stays on SQLite (RLS not enforceable there; app-layer
  scoping still covered); a marker-gated **Postgres integration** suite proves
  cross-tenant denial connecting as `gummy_app`.
- **Rollout:** deploy `0005` in a window, switch app to `gummy_app`, verify the GUC
  fires per transaction, then enforce. RLS sits on top of existing app-layer
  scoping → defense-in-depth, fail-closed. Rollback = downgrade `0005` + revert the
  connection role.

---

## 5. Cross-Cutting

- **New runtime dependency:** `pyjwt[crypto]` (Increment A).
- **Quality gate:** Ruff/Black/mypy/pytest stay green throughout; the suite remains
  hermetic and offline.
- **Security-by-default principle** ([CONVENTIONS.md §6](../CONVENTIONS.md)): every
  change fails closed — auth rejects (401), RLS hides (no rows) — never opens.

## 6. Open Questions (to confirm before implementation)

1. **Signing scheme:** is this Supabase project on the **legacy JWT secret (HS256)**
   or **asymmetric signing keys (JWKS)**? (Determines whether the JWKS path is
   needed in Increment A or can be deferred.)
2. **Identity for legacy dev data:** discard the pre-auth verification rows, or
   re-key them to a real Supabase `sub`?
3. **Frontend timeline:** will a real supabase-js client exist to exercise tokens
   during Increment A, or do we validate solely with minted/REST tokens until then?

---

_Related: [PHASE1_VERIFICATION.md](PHASE1_VERIFICATION.md),
[PHASE1_PROGRESS.md](PHASE1_PROGRESS.md),
[../architecture/security-system.md](../architecture/security-system.md),
[../architecture/system-design.md](../architecture/system-design.md)._
