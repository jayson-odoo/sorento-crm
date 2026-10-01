# UAC: NS-SMOKE-ALL-ROUTES (never-stuck guard G4)

Plan: `PLAN-ns-smoke-all-routes.md`.

1. The spec visits every `page.tsx` route under `app/(protected)` except the Metronic demo dirs
   (`/public-profile`, `/network`, `/dark-sidebar`, `/i18n-test`), once per persona: admin,
   restricted, expired. A new `page.tsx` joins with no registration.
2. Admin / restricted: a visible `[data-loading]` element or a spinner outside a button 15 s after
   navigation fails the route with "still loading after 15s".
3. Expired: a route not on `/signin` within 5 s fails with "expired session not on /signin".
4. Restricted: a 403 from `/api/v1/` plus empty / not-found copy and no `AccessDenied` on screen
   fails with "refusal rendered as empty" naming the refused endpoint(s).
5. Any persona: `Permission required:`, `One of these permissions required` or
   `Module not enabled:` on screen fails with "raw permission text on screen".
6. Admin / restricted landing on `/signin` fails with "live session bounced to /signin".
7. Each entry in `known-failures.json` carries an audit row id; it runs as an expected failure,
   and passing turns the night red with "known failure now passing".
8. The nightly job runs on cron and on dispatch only, never on a PR or push, and skips itself
   when main's head already has a green run. Its summary lists new failures first, then known
   failures now passing, then counts; screenshots are in the `never-stuck-report` artifact.
9. The seed script refuses any `DATABASE_URL` whose host is not localhost.
10. `npm run test:e2e` (the default config) does not pick up the smoke spec.
