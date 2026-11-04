# PLAN: client error report + stale-chunk self-heal (CLIENT-ERROR-REPORT)

Status: in progress (small fix track: one new table, no auth/RBAC change beyond one new view slug)

## Why

4 Nov, prod, a "Stock Inquiries" tab showed the root crash screen ("Something went wrong / The app
could not start"). That screen is `components/common/GlobalErrorView.tsx`, mounted only by
`app/global-error.tsx`. It logs `console.error` and nothing else, so nobody can see why it happened.
The commonest cause is a stale chunk (a deploy replaced the build the tab runs), which a single
reload fixes, but the root boundary did not use `isChunkLoadError` and never reloaded by itself.

## Build

1. `client_error_report` table (additive migration): user id (nullable), error name, message, stack
   (truncated), digest, URL path (no query string), build sha, user agent, `is_chunk_error`,
   boundary (`global` | `protected`), client timestamp, created_at.
2. `POST /api/v1/client-errors` (authenticated staff session or API key principal): validates and
   truncates every field server-side, strips query string and fragment from the path, rate-limited
   per user (Redis fixed window, fails open when Redis is down), stores one row. 204.
   Unauthenticated pages do not report (the boundary skips when there is no token).
3. `GET /api/v1/system/client-errors` gated by new permission `system_management.client_error.view`.
4. Retention: rows deleted after 30 days by the existing daily `api_call_log_prune` task (no new
   scheduled task row).
5. FE: `lib/client-error-report.ts` (dependency-free: fetch + token lookup), called once per error
   by `app/global-error.tsx` and `app/(protected)/error.tsx`.
6. FE: `global-error.tsx` reloads once on a chunk load error, guarded in sessionStorage by build sha
   so it can never loop; if the reloaded page fails again the screen shows. Reload button stays.
7. FE: System Management > Client Errors list, modelled on the API call log page.

## Tests (red first)

- vitest: chunk error -> one reload, no screen; second chunk error same build -> screen, no reload;
  real error -> report posted once, no reload; no token -> nothing posted.
- pytest: post stores row with query stripped and fields truncated; oversize body rejected; rate
  limit returns 429 after N; list requires permission; prune deletes rows past 30 days.
