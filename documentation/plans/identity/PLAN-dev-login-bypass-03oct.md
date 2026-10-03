# PLAN: Dev auto-login for local test copies (DEV-LOGIN-BYPASS)

Status: Plan (behaviour card asked, awaiting owner answers). Track: full (auth change, security review mandatory).

Owner ask (3 Oct 2026): "a dev mode to bypass all these logins for hand testing, to boost our
productivity". Crew runs local test copies (FE `http://<lane>.localhost:31xx`, BE `:81xx`,
NextAuth v4, per-lane cookie suffix). Signing in on every copy is slow, and the automated tester
refuses to type credentials into sign-in forms.

## Behaviour card (proposed)

Visiting a test copy with the flag on lands you signed in as the default dev user (an admin).
The sign-in page grows a "Sign in as" picker listing only the allowlisted dev users (name + role,
never an id) so a tester can switch to a view-only user. After an explicit sign-out the picker
shows instead of auto-signing you straight back in.

## Design (recommended: BE dev endpoint + FE NextAuth provider, both guarded)

- **Backend** `POST /api/v1/auth/dev-login {email}` mints the SAME `user_sessions` row as
  `/auth/login` (`mint_session`, `build_login_response`) for an allowlisted ACTIVE user, and
  `GET /api/v1/auth/dev-login/users` lists the allowlist (name, email, role name). Both answer a
  plain 404 unless every guard holds, so the route is indistinguishable from absent in prod.
- **Frontend** a third NextAuth `CredentialsProvider` (`id: 'dev-login'`) whose `authorize()`
  takes only an email, re-checks the FE-side guards, and posts to the backend endpoint. No
  password or secret reaches the browser; the browser holds the normal NextAuth cookie only.
- **Sign-in page** a server-side check decides whether to render the picker; auto-submit of the
  default user fires once per tab (sessionStorage) so sign-out still lets you switch.

## Guards (all must hold; fail closed)

Backend (`app/services/dev_login_guard.py`):
1. `DEV_AUTO_LOGIN=true` (exact, case-insensitive true/1/yes). Default off.
2. `ENVIRONMENT` in an allowlist (`development`, `dev`, `local`, `test`); anything else,
   including unset-to-production, refuses.
3. Request `Host` header hostname is `localhost`, `*.localhost`, or `127.0.0.1`.
4. Request client IP is loopback (the FE server calls the BE on localhost; a deployed BE behind
   Docker/Nginx sees a non-loopback peer).
5. Startup: `DEV_AUTO_LOGIN` on while `ENVIRONMENT` is production/prod/staging raises at startup
   (crash), and an active flag logs a loud WARNING banner.

Frontend (`lib/dev-login.ts`):
1. `DEV_AUTO_LOGIN=true` (server-only env, never `NEXT_PUBLIC_*`).
2. `NODE_ENV !== 'production'` (a prod build cannot carry it).
3. Browser request `Host` is localhost / *.localhost / 127.0.0.1.

CI/deploy guard: a pytest scans `sorento_crm/docker-compose.yml`, `.github/workflows/*.yml`,
and every committed `.env.production*` / `.env.staging*` for `DEV_AUTO_LOGIN`; any hit fails.

## Users selectable

`DEV_AUTO_LOGIN_USERS` = comma list of emails (first = default). Only ACTIVE, non-trashed users
in that list can be signed in; any other email answers 404. No list = feature inert.

## How crew enables it

`crew.toml` env_overrides for sorento copies set, for BE: `DEV_AUTO_LOGIN=true`,
`DEV_AUTO_LOGIN_USERS=<admin email>,<view-only email>` (ENVIRONMENT stays `development`);
for FE: `DEV_AUTO_LOGIN=true`.

## Open questions (see the crew-ask on the PR)

1. Session `auth_method`: add `dev_login` to `ck_user_sessions_auth_method` (one migration) vs
   reuse `password`. Rec: add it, so dev sessions are visible in audit.
2. FE guard `NODE_ENV !== 'production'`: do crew copies run `npm run dev`? Rec: yes, require it.
3. User allowlist by env emails vs a dedicated seeded set of dev users. Rec: env emails.
4. Auto-login once per tab vs every visit to /signin. Rec: once per tab.

## Tests (red first)

BE pytest: each guard off → 404 (flag, env, host, client ip, email not allowlisted, inactive
user); all on → 200 with a session row that `get_current_user` resolves; startup assertion raises
for production; compose/workflow scan. FE vitest: guard helper truth table; provider refuses when
any FE guard fails; sign-in page renders picker only when enabled.
