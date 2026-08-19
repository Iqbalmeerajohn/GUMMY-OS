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

## 6. Password recovery

The login screen linked to `/forgot-password` from the day local auth landed,
but nothing served it — no page, no endpoint, no table. Clicking it produced a
404. This is the flow that closes it.

### The token is never stored

```
secrets.token_urlsafe(32)  ->  raw token  ->  the emailed link
                                   |
                               sha256()
                                   |
                        password_reset_tokens.token_hash
```

Redemption hashes what was presented and looks *that* up, so a dump of
`password_reset_tokens` grants nobody a reset. This mirrors `refresh_tokens`
exactly, and for the same reason: the token is 256 bits of cryptographic
randomness with no guessable structure, so a plain SHA-256 is correct — no
KDF needed — and the lookup stays a single indexed read.

A reset token is, for its lifetime, a password. So the guarantees are about how
it stops working:

| Property | How |
| --- | --- |
| Single-use | `used_at` stamped on redemption; a spent row is never accepted again |
| Short-lived | `PASSWORD_RESET_TTL_MINUTES`, default **45** |
| One account only | `user_id` FK; the token resolves to its own row or nothing |
| Superseded by a new request | requesting a second link marks the first used |
| Sessions die with it | every `refresh_token` for the user is revoked on success |

Rows are marked spent rather than deleted, so redemption can tell "never
issued" apart from "already used", and the spent row remains as evidence.

### No account enumeration

`POST /api/v1/auth/forgot-password` returns the **same body and status** for an
address that has an account and one that does not:

```json
{ "message": "If an account exists for this email, password reset instructions have been sent." }
```

Asserted as equality, not similarity, in `tests/test_password_reset.py`. Every
token failure — unknown, expired, spent, orphaned — returns one message too, so
an attacker cannot probe which tokens once existed.

A **Google-only account** (no `password_hash`) gets no token at all: minting one
would silently convert it into a password account. The response stays generic,
so this is invisible to the caller.

### Endpoints

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/forgot-password` | `{email}` | 200, generic message |
| POST | `/api/v1/auth/reset-password` | `{token, new_password}` | 200, or 400 invalid/expired, or 422 weak password |

Reset does **not** issue a session. The user signs in with the new password,
which proves the reset worked.

A 422 (password too short) does **not** spend the token — that is the user
mistyping, and burning their only link over it would strand them.

### Password policy is shared, not re-specified

One `Password` type in `app/schemas/auth.py` (8–128 characters), used by both
`SignUpRequest` and `ResetPasswordRequest`. The frontend mirrors it in
`lib/auth/passwordPolicy.ts`, used by both the signup and reset forms. A reset
flow that re-specifies the bounds is how an app ends up accepting a weaker
password on recovery than it ever allowed at sign-up.

### Email delivery: console by default

There was no email layer before this, and a local-first app must not require an
email account to run. Delivery is a mode, not a dependency.

| `AUTH_EMAIL_MODE` | Behaviour |
| --- | --- |
| `console` (default) | The message — reset link and all — is written to the backend log, tagged `[GUMMY AUTH]`. **Local development.** Nothing is sent, and nothing claims to have been. |
| `smtp` | A real send via `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM`. **Optional production delivery.** |

An unrecognised mode is rejected at startup rather than falling back to console
— otherwise a deployment that meant to send email would log links forever and
look like it was working. In SMTP mode a failed send surfaces as a 502; it is
never reported as success. Failure logs record the exception type and host, not
the response body, because some providers echo the username back.

The reset screen asks the backend which mode it is in and, in console mode
only, tells the developer where the link actually went. The success copy itself
is identical either way.

---

## 7. User isolation

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

## 8. Verification

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

## 9. Known limitations

- **Google sign-in is unverified end to end** — no credentials on this machine.
- **`aud` is not checked** on the Google ID token (defence in depth, not a hole).
- **Tokens live in localStorage**, so XSS in the app would expose a session.
- **No rate limiting** on `/auth/login` or `/auth/forgot-password` — a local-only concern today, blocking
  for any hosted deployment.
- **Email delivery is console-mode locally.** SMTP mode is implemented and
  unit-tested, but no real SMTP send has been performed from this machine.
- **The auth engine bypasses RLS** by necessity; its safety rests on query
  discipline (§6).
