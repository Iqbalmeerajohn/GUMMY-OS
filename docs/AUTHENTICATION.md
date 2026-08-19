# Authentication

GUMMY is its own identity provider. No Supabase, no Auth0, no external identity
service — verified by grep: zero references in `backend/app` or `frontend/src`.

---

## 1. Architecture

```
Browser (localStorage)
   │  Authorization: Bearer <access token>
   ▼
FastAPI  ──►  verify HS256 locally (no DB read, no network call)
   │          set app.current_user_id (per-request ContextVar)
   ▼
PostgreSQL  ──►  RLS policies key on that GUC, fail-closed
```

| Element | Implementation |
| --- | --- |
| Access token | HS256 JWT, audience `gummy-os`, issuer `gummy-os-local`, 60-min TTL |
| Verification | Local secret — **no database read, no network call**, so auth is off the latency budget and works offline |
| Refresh token | 30-day, **stored hashed**, **rotating** — presenting one revokes it |
| Password | PBKDF2-HMAC-SHA256, **600,000 iterations** (OWASP), 16-byte salt, `hmac.compare_digest`, self-describing format supporting transparent rehash |
| Google | Authorization-code flow direct to Google, signed-JWT `state`, tokens returned in the URL **fragment** |
| Tenant isolation | Postgres RLS on `app.current_user_id`, set per transaction, cleared per request |

**One issuer, one algorithm.** There is no second verifier, so there is no key
routing and therefore no algorithm-confusion surface to defend.

---

## 2. Sign-out — the bug that was fixed

Sign-out was reported broken. It was, and the cause was not in the client.

With `GUMMY_OWNER_MODE=true`, a request carrying **no credential at all**
returned HTTP 200 with the owner account. Measured against the running app:

```
GET /api/v1/auth/me          (no Authorization header)  → 200  owner
GET /api/v1/memories         (no Authorization header)  → 200  7 records
GET /api/v1/conversations    (no Authorization header)  → 200  10 records
```

So logging out could not work by construction. The client discards its token,
asks the server who it is, and is told it is still the owner — which is exactly
the reported symptom: the previous user's name persisting after sign-out.

It was also a data exposure in that configuration: anything that could reach
the API read the owner's memories with no credential.

### What owner mode is for

A personal single-user machine that should never see a login screen. Unlike
`AUTH_DEV_BYPASS`, it resolves a **real persisted account**, so anything GUMMY
learns while running open stays owned by that account once sign-in is enabled.
That is a legitimate feature.

### The fix

Owner mode's premise is *"one person uses this machine"* — and that premise is
checkable.

1. **Gated on being the only account.** The moment a second account exists the
   premise is false, so the dependency stops auto-authenticating and rejects
   the request like any other unauthenticated one. Answering an anonymous
   request with the owner's identity on a shared install is a data leak, not a
   convenience.
2. **Startup warning** naming the consequence, so it is never a silent surprise.
3. **Documented at the setting**, in `config.py` and both `.env.example` files:
   owner mode and sign-out are mutually exclusive.
4. **Turned off locally** (`GUMMY_OWNER_MODE=false`), which is the setting for
   real accounts.

**Owner mode and sign-out cannot both work.** Leave it `false` unless you want a
machine with no login screen and no sign-out.

---

## 3. Session lifecycle

```
signup / login  → access token (60 min) + refresh token (30 days, hashed)
                  stored in localStorage
request         → Bearer token, verified locally
near expiry     → transparent refresh, single in-flight promise shared by all
                  callers (rotation would otherwise reject the losers)
sign-out        → server revokes the refresh token
                  client clears localStorage and the whole query cache
after sign-out  → no credential → 401 → login screen
```

**The backend is authoritative.** The client never treats cached UI state as
proof of authentication; `/auth/me` decides.

**Why localStorage:** an httpOnly cookie resists XSS better but requires the API
and the app to share an origin, which the `:3000` → `:8000` split precludes. The
refresh token is revocable server-side, which bounds the damage. Revisit if
GUMMY is ever served from one origin.

---

## 4. Display names

- Given at signup and **kept**. Never inferred from the email local-part —
  `jane.doe@example.com` does not become "Jane".
- **Not overwritten on login.** An existing user's name is stable.
- From Google, taken from the verified `name` claim when present.

---

## 5. Google sign-in

**Implemented in code; not configured on this machine.** The button is hidden
until the backend reports credentials, because offering a control that 503s on
click is worse than not offering it — the user cannot tell it is a server
configuration gap rather than their own mistake.

```
GET  /api/v1/auth/config          → { google_enabled: false }
GET  /api/v1/auth/google/start    → 503 while unconfigured
GET  /api/v1/auth/google/callback → exchanges the code, mints a session
```

### Identity key

Keyed on Google's **`sub`** claim, not email. `sub` is stable per (account,
OAuth client) and never reused; email can be changed and reassigned. Keying on
email would merge two people who ever shared an address, and split one person
who changed theirs.

### Design notes

- **`state` is a signed, short-lived JWT** rather than a server-side session
  entry, so CSRF protection needs no shared store — which matters because the
  callback may be handled by a different worker than the one that started the
  flow.
- **Tokens return in the URL fragment**, which browsers never send to servers
  and which never appears in logs or `Referer` headers.
- The ID token's signature is not re-verified: it arrives in the body of a
  direct TLS response from Google's token endpoint, which is Google's own
  documented guidance for the authorization-code flow. *Verifying `aud ==
  client_id` would still be cheap defence in depth and is not currently done.*

### To enable it

1. Google Cloud Console → **APIs & Services → Credentials → Create credentials →
   OAuth client ID → Web application**.
2. Authorised redirect URI — exactly:
   `http://localhost:8000/api/v1/auth/google/callback`
3. Put the two values in **`backend/.env`** (gitignored):
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```
4. Restart the backend. The button appears automatically once
   `/auth/config` reports `google_enabled: true`.

**Never commit these.** `.env` is gitignored; `.env.example` carries empty
placeholders only.

---

## 6. User isolation

Enforced at three independent layers:

| Layer | Mechanism |
| --- | --- |
| HTTP | `user_id` comes from the verified token, never from a request parameter |
| Service / repository | Every query is filtered by that id |
| Database | RLS on all 24 tenant tables, keyed on the per-transaction GUC, **fail-closed** (`NULLIF(...)::uuid` → NULL → no rows) |

The application connects as `gummy_app` (`NOSUPERUSER NOBYPASSRLS`), so even a
missed filter in application code cannot read another tenant's rows.

**One deliberate exception:** `get_auth_engine()` uses the owner connection,
because a sign-in must find an account *by email before any tenant is known*,
which on the RLS-scoped connection matches zero rows. The safety property is
that every query on that engine filters explicitly by email, id, or `google_sub`
and returns a single row. That is enforced by code discipline, not by the
database — a future unfiltered query there would read every user.

---

## 7. Verification

Live, against the running stack — **26/26**. See
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

| Check | Result |
| --- | --- |
| Anonymous `/auth/me` | 401 |
| Anonymous memories / conversations / automations | 401 |
| Sign-out revokes the refresh token | replay → 401 |
| After sign-out, anonymous request | 401 |
| User B sees none of A's memories, conversations, or goals | 0 / 0 / 0 |
| B fetching A's conversation by id | 404 |
| A logs back in, identity and data intact | ✅ |
| Display names stable across sign-out and re-login | ✅ |
| `google/start` while unconfigured | 503, no crash |

Automated: **22 tests** in `tests/test_auth_lifecycle.py`, plus the pre-existing
auth suites.

**Not covered automatically:** the Google OAuth round trip. It needs a real
browser and real Google credentials, so it is documented as manual and is *not*
claimed as tested.

---

## 8. Known limitations

- **Google sign-in is unverified end to end** — no credentials on this machine.
- **`aud` is not checked** on the Google ID token (defence in depth, not a hole).
- **Tokens live in localStorage**, so XSS in the app would expose a session.
- **No rate limiting** on `/auth/login` — a local-only concern today, blocking
  for any hosted deployment.
- **No password reset flow.**
- **The auth engine bypasses RLS** by necessity; its safety rests on query
  discipline (§6).
