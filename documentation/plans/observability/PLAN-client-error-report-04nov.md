# PLAN: client error report + stale-chunk self-heal + Safari start crash (CLIENT-ERROR-REPORT)

Status: built, in review (full track: migration, new permission slug, new authenticated ingest
surface; security review ran). UAC: `client-error-report-acceptance-criteria.md`.

## Why

4 Nov, prod, a "Stock Inquiries" tab on a MacBook in Safari showed the root crash screen
("Something went wrong / The app could not start"); Chrome worked. That screen is
`components/common/GlobalErrorView.tsx`, mounted only by `app/global-error.tsx`. It logged
`console.error` and nothing else, so nobody could see why. The root boundary also never used
`isChunkLoadError`, so a stale build (the commonest cause in Chrome) never healed itself.

Crew reproduced the Safari case with Playwright WebKit: `providers/settings-provider.tsx` threw on
mount, on every page including sign-in, for two reasons: `structuredClone` is missing before Safari
15.4, and `Object.keys(localStorage)` throws SecurityError when Safari blocks website storage.

## Built

1. `client_error_report` table (migration `cer_0001_client_error_report`, additive): user id
   (nullable), boundary (`global` | `protected`), error name, message, stack, digest, path (no query
   string), build sha, user agent (from the request header), `is_chunk_error`, client timestamp,
   created_at. Permission `system_management.client_error.view` (not granted to any role; admins pass).
2. `POST /api/v1/system/client-errors` (any signed-in principal): body streamed and refused above
   16 KB, every field capped server-side, link tokens redacted in path, message and stack, NUL
   stripped, bad client timestamp ignored. Rate limit 20 rows per user per rolling hour, counted from
   the table itself (no Redis). 204 / 413 / 422 / 429.
3. `GET /api/v1/system/client-errors` behind the view slug; user ids resolved to names.
4. Retention: rows deleted after 30 days by the existing daily `api_call_log_prune` task (its own
   try block, so an api_call_log failure cannot skip it). No new scheduled task row.
5. FE reporter `lib/client-error-report.ts`: plain fetch (no shared chunks), one report per error
   object, skips signed-out pages, `keepalive` with a retry without it for older Safari.
6. `app/global-error.tsx`: chunk load error reloads once (sessionStorage key per build sha, so it can
   never loop; no storage means no auto reload), screen and report only if that did not fix it.
   Reload button kept. `app/(protected)/error.tsx` reports too.
7. Build sha: `NEXT_PUBLIC_BUILD_SHA` from the deploy workflow build-arg into the frontend Dockerfile.
8. System Management > Operations > Client Errors list + detail drawer.
9. Safari: `SettingsProvider` copies defaults with JSON instead of `structuredClone` and keeps every
   storage access in try (in-memory fallback). Guard test over the root providers and shell files.

Choice made on purpose: a stale chunk the automatic reload fixes is not reported (the request would
race the reload); only crashes the reader actually saw are recorded.

## Tests

- vitest: `app/global-error.selfheal.test.tsx`, `lib/client-error-report.test.ts`,
  `app/(protected)/error.test.tsx`, `providers/settings-provider.safari.test.tsx`,
  `components/rootProviders.safariGuard.test.ts`.
- pytest: `tests/test_client_error_report.py`.
