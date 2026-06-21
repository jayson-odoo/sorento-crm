# PLAN — Staff rolling sessions + FastAPI-owned auth (remove Prisma)

**Status:** Implemented on `feature/staff-rolling-sessions-fastapi-auth` (worktree). Backend + FE + tests written, green locally (pytest sessions 14/14, vitest devices 6/6, tsc 0 errors). PENDING on return: `alembic upgrade head` (migration 237), `npm install --force` + FE rebuild, browser E2E + a Playwright spec. Hard cutover — all staff re-login once on deploy.
**Branch:** `feature/staff-rolling-sessions-fastapi-auth`
**Owner:** jayson

## Problem

Staff login logs users out after a fixed 24h regardless of activity. NextAuth uses
`strategy:'jwt'`, `maxAge: 24h` **absolute**, no rolling. The "Remember me" checkbox is
**dead UI** — `rememberMe` is collected in `signin/page.tsx` and declared on the
credentials provider but **never used** in `authorize()`. Result: hard logout every 24h,
and remember-me does nothing.

User wants staff login to behave like the **portal**: same device kept in use keeps
extending validity over a rolling 30-day window, no re-prompt, with a real "remember me".

## Decisions (from grill)

| # | Decision |
|---|----------|
| Q1 | **No OTP for staff.** Login stays email+password. "Won't prompt to re-login" = don't force re-entry while the same browser keeps being used. |
| Q2 | **"Remember me" becomes real** (checked = persistent rolling; unchecked = short). |
| Q3 | **Revocable sessions**, not stateless JWT. Privileged staff need instant kill (offboarding / stolen device / log-out-all). |
| Q4→Q6 | **Remove Prisma entirely; FastAPI owns auth.** FastAPI already has `/api/v1/auth.py` (`/login` bcrypt, signup, reset, verify) + JWT validation + the same `users` table (same Postgres, same UUIDs — Prisma rows ARE the FastAPI rows). The FE Prisma password path is a duplicate. Build the session store **once** in FastAPI. |
| — | **No Google login** (confirmed unused) → delete `GoogleProvider`. This removes the only thing that needed a new FastAPI endpoint, so Prisma goes in this ticket, not staged. |
| Q7 | **Keep NextAuth as a thin shell** — `strategy:'jwt'`, **no adapter, no Prisma**. `authorize()` calls FastAPI `/login`; the FastAPI session token rides inside the NextAuth httpOnly cookie. `useSession()`, `signIn`, `(protected)` layout, impersonation hydration, the api-proxy bridge all stay. |
| Q8 | **Opaque DB session token — exact `PortalToken` clone.** Random string, row in `user_sessions`, looked up per request. NOT a JWT-access/refresh split (B's 15-min revoke lag defeats Q3). |
| Q8 note | `get_current_user` loads the user from the DB via the session row → **role/permission changes take effect immediately** (no stale-JWT window). |
| Q10 | Remember-me **checked → `expires_at = now+30d`, rolling**. **Unchecked → `now+8h`, no roll** (server-authoritative; no NextAuth per-login cookie hacking). |
| Q11 | **No absolute cap** — pure sliding, exactly like portal. Revocation is the safety lever, not a hard ceiling. |
| Q12 | Revocation (all built, incl. UI): (1) logout → revoke this session; (2) password change/reset → revoke ALL; (3) admin disable/block (`status != ACTIVE`) → revoke ALL + per-request status check rejects instantly; (4) self-service **"log out all devices"** + admin **force-logout**. |
| Q13 | **Active-sessions list UI** (Google "Your devices" pattern). `user_sessions` stores `user_agent`, `ip_address`, `last_seen_at`. Per-row revoke + revoke-all. No UUIDs/tokens in UI — friendly device label parsed from UA. |
| Q14 | **Hard cutover.** On deploy every staff member re-logs in once (no session row for old cookies). Legacy `_decode_jwt_user` staff path retired. External `X-API-Key` and portal `X-Portal-Token` paths untouched. |
| Q15 | **Global 401 interceptor** in `lib/api-client`: a `session_revoked` / `session_expired` code → NextAuth `signOut()` + redirect to `/signin?callbackUrl=…`. Gated on the specific code so RBAC 403s / flaky 401s don't log everyone out. (No idle-tab heartbeat — A only.) |
| Q16 | **Basic brute-force throttle** on FastAPI `/login`: per-email + per-IP, ~15 min lock after ~5–10 fails, clear message. No CAPTCHA this ticket. Counters in **Redis** (TTL-friendly, already in stack). |
| Q17 | **Impersonation unchanged** — header-based (`X-Impersonate-User-Id`), `ImpersonationSession` untouched. Session-row check runs against the **admin's** token first, then the impersonation override applies → revoking the admin kills their impersonation. |

## Throttle/constant values

- Rolling window (verified/checked): **30d**. Slide threshold: **29d** (write ~once/active-day) — clone `PORTAL_SLIDE_THRESHOLD`.
- Unchecked: **8h**, `rolling=false`.
- `last_seen_at`: separate **~10 min** throttle (so the device list isn't a day stale) — independent of the 29d `expires_at` slide.
- NextAuth cookie `maxAge`: **≥30d** so the cookie outlives the FastAPI session; FastAPI is the real authority on validity.

## Backend work (`sorento_crm_backend/`)

1. **Model + migration** `user_sessions` (mirror `portal_tokens`):
   `id, user_id (FK users), token (unique, indexed), expires_at, revoked_at, rolling (bool),
   user_agent, ip_address, last_seen_at, created_at`. Index on `token`; index on `user_id`.
2. **`/api/v1/auth.py` `/login`**: after bcrypt verify, create a `user_sessions` row
   (expiry per `remember_me`), capture UA/IP, return the opaque token + user payload.
   Add brute-force throttle (Redis).
3. **`dependencies.py get_current_user`**: treat `Authorization: Bearer <opaque>` as a session
   token → look up row → reject `revoked_at`/expired with body `{code:"session_revoked"|"session_expired"}`
   → load user, reject `status != ACTIVE` → slide `expires_at` (29d throttle) + `last_seen_at`
   (10 min throttle). Apply impersonation override AFTER the session check. Wrap any naive-UTC
   datetimes with `_to_aware_utc()` (known `create_event_log` gotcha).
4. **Revocation service** `revoke_all_for_user(user_id, except_session_id=None)` + single-session revoke.
   Wire into: logout, password change/reset, status→blocked, admin force-logout.
5. **Endpoints**: `GET /sessions` (list own active sessions), `DELETE /sessions/{id}`,
   `POST /sessions/revoke-all` (all but current), admin `POST /users/{id}/force-logout`.
6. Retire staff use of `_decode_jwt_user` (keep for nothing — external uses X-API-Key).

## Frontend work (`sorento_crm_frontend/`)

1. **`auth-options.ts`**: delete `PrismaAdapter`, `GoogleProvider`, all `prisma.*` calls.
   `authorize()` → POST FastAPI `/login` with `{email, password, rememberMe}` → store returned
   opaque token + user in the JWT. Set `session.maxAge` ≥30d.
2. **`lib/prisma.ts`, `prisma/schema.prisma`, `prisma/seed.js`, `prisma/setup.js`** — delete.
   Drop deps `@prisma/client`, `prisma`, `@next-auth/prisma-adapter`. Remove prisma scripts from `package.json`.
3. **`/api/auth/token` + `lib/api-proxy.ts`**: forward the stored **opaque token** to FastAPI
   (stop re-signing an HS256 JWT). Keep `sessionTokenCookieName()` wiring.
4. **`signin/page.tsx`**: keep the real "Remember me" checkbox; it now drives `/login` expiry.
5. **`lib/api-client`**: global 401 interceptor on `session_revoked`/`session_expired` → `signOut()` + redirect.
6. **Settings → Sessions/Devices page**: active-session list (device label from UA, IP, last-active,
   "this device", per-row revoke, "log out all other devices").
7. **Admin user-management**: "Force logout" action per user.

## Testing (Phase 2 — lands with the wiring, per three-phase loop)

- **pytest**: `/login` happy/lock/invalid; session slide + 29d throttle; revoke-all on password change /
  block; `get_current_user` rejects revoked/expired/blocked with the right code; impersonation after revoke.
- **vitest**: device-list states (loading/empty/data), remember-me wiring, 401-interceptor signOut.
- **playwright**: login → stays in past old 24h (simulated), remember-me unchecked expiry behavior,
  log-out-all-devices kicks the other session, admin force-logout. Verify via sidebar nav (not deep URL).

## Rollout

Hard cutover. Announce "log in again after the update." One deploy; no dual-auth transition code.

## Open / deferred

- Idle-tab heartbeat (Q15 option B) — deferred.
- Absolute session cap (Q11 option B) — one `created_at` check if compliance later needs it.
- CAPTCHA / IP reputation on login — out of scope.
