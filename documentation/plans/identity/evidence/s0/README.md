# S0 browser-verification evidence (identity, #1280)

Date: 2026-09-26
Commit verified: `097f7655` (branch `claude/identity-s0-model-ulpowm`)
Scope: AC-13 and the S0 done-when "audit screens show actor words, including contact, at
375px and 1280px" (`documentation/plans/identity/s0-contract.md` section 5).

## Environment

- Cloud VM Postgres `sorento_ci` (schema at alembic head `identity_0001_s0_model`), Redis.
- Backend: `venv/bin/uvicorn app.main:app` with `SORENTO_ENV_FILE=.env.ci-tests`, port 8000.
- Frontend: `npm run dev` (Turbopack), port 3000, `.env.local` (gitignored) pointing
  `FASTAPI_INTERNAL_URL` at the backend so browser calls to `/api/v1/*` proxy through Next's
  dev rewrite (`NEXT_PUBLIC_API_URL` left unset, relative paths).
- Browser: agent-browser 0.27.0, headless Chromium at `/opt/pw-browsers/chromium-1194`
  (agent-browser's own Chrome download was blocked by the sandbox's egress policy - see
  "Environment notes" below), session name `s0-evidence`.
- Seed script: `/tmp/claude-0/seed_s0_evidence.py` (not committed - scratch only). Created a
  superadmin login, users Aisyah/Nurain/Ops Bot, RespondContact "Aisyah Rahman", Integration
  "n8n" acting as Ops Bot, one Product ("S0 Evidence Product" / `S0-EVIDENCE-001`), and one
  `audit_logs` row per actor kind against that product. Also enabled the `base` and `product`
  tenant modules (`app.modules.runtime.installer.install_modules`) - a fresh tenant has zero
  module rows, which hides the whole "System" and "Products" sidebar groups client-side; this
  is expected behaviour for a real installed tenant, not an S0 defect, so it needed doing once
  for the sidebar to render at all.

## Navigation path (sidebar clicks from `/`, no deep links)

Dashboards (home) -> **System** group (Administration section) -> **Operations** -> **Audit
Logs** (`/system-management/audit-logs`). For the record's own trail: **Products** group ->
**Products** -> **All Products** -> search `S0-EVIDENCE-001` -> product detail -> **Audit
Trail** tab.

## Checks and results

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Audit Logs list Actor column shows actor words at 1280px, no UUID | PASS | `audit-logs-list-1280.png` - Actor column shows "Aisyah (email)", "Nurain", "Nurain on behalf o...", "Integration: n8n as...", "Background job for...", "Aisyah (phone)", "System", "Public link" |
| 2 | Same at 375px, page not horizontally clipped | PASS | `audit-logs-list-375.png` (grid scrolled to the Actor column via its own internal horizontal scrollbar - `document.documentElement.scrollWidth === clientWidth` measured 360/360, no page-level overflow) |
| 3 | Contact-row detail drawer: Actor / Actor kind / Sign-in method, 1280px | PASS | `audit-logs-drawer-contact-1280.png` - Actor "Portal: Aisyah Rahman (no user)", Actor kind "Portal contact", Sign-in method "Portal token" |
| 4 | Contact-row detail drawer, 375px, not clipped | PASS | `audit-logs-drawer-contact-375.png` - same three fields render, wrapped not cut; dialog measured 373/375 clientWidth/scrollWidth |
| 5 | Integration-row detail drawer: Actor / Actor kind / Sign-in method, 1280px | PASS | `audit-logs-drawer-integration-1280.png` - Actor "Integration: n8n as Ops Bot", Actor kind "Integration", Sign-in method "API key" |
| 6 | No UUID-shaped string in the Actor column or drawer actor rows | PASS | Confirmed by reading the accessibility-tree cell text for every seeded row (`get text`/snapshot) and visually in both drawer screenshots - every Actor/Actor kind/Sign-in method value is a word, never `user_id`/`entity_id` |
| 7 | Record's own Audit Trail (`components/audit/AuditTrail.tsx`) shows "by <actor_label>", 1280px | PASS | `record-audit-trail-1280.png` on the Product detail page ("S0 Evidence Product"), Audit Trail tab: "by Aisyah (phone)", "by Aisyah (email)", "by Nurain on behalf of Aisyah", "by Integration: n8n as Ops Bot", "by Background job for Aisyah", "by Scheduled: daily reorder run" |
| 8 | Same at 375px, not clipped | PASS | `record-audit-trail-375.png` - all six lines wrap and read in full; page `scrollWidth === clientWidth` (360/360) |
| 9 | Console/errors clean, correct `/api/v1/audit/logs/` network call fires | PASS | `console`/`errors` showed no warnings/errors beyond routine Fast Refresh/i18next logs; `network requests --filter /api/v1/audit` showed `GET /api/v1/audit/logs/?page=1&limit=50 200` |

All 9 checks pass. Every actor kind in the contract's section-5 table (`user` with each
`auth_method`, `user` impersonating, `integration`, `worker`, `scheduler`, `contact`,
`public_link`, `system`, `legacy`) was exercised and matched the literal wording specified.

## Environment notes (not defects in the S0 diff)

- **Chrome download blocked**: `agent-browser install` could not reach
  `googlechromelabs.github.io` (sandbox egress policy, 403). Worked around by pointing
  agent-browser at the Playwright Chromium already present at
  `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` via `--executable-path` on every
  command (the daemon reuses one browser process per session once opened).
- **Fresh-tenant sidebar**: a brand-new tenant has no `tenant_modules` rows, so
  `useTenantModules()` resolves an empty enabled-module set and `filterMenuByModule` hides
  every group carrying a `moduleKey` (including "System", parent of "Audit Logs"). Enabled
  `base` + `product` via `install_modules()` once, in the seed step, rather than in app code -
  this is normal onboarding, not part of the S0 diff.
- **Mid-walk data reset**: partway through the walk, the 10 seeded `audit_logs` rows for the
  product entity were found reset to `actor_type='legacy'` with `auth_method`/`job_id`/etc.
  back to column defaults, while the users/product/contact/integration rows seeded alongside
  them were untouched. This matches an `ALTER TABLE ... ADD COLUMN ... DEFAULT` cycle
  retroactively stamping existing rows - i.e. something else re-ran the S0 migration's
  downgrade/upgrade (or an equivalent schema replay) against this same shared `sorento_ci` DB
  while this verification was in flight, most likely a concurrent pytest run against the same
  `.env.ci-tests` database from another agent on this lane. Re-seeding just the audit rows
  (`/tmp/claude-0/reseed_audit_only.py`) restored the correct data and every screenshot in this
  folder was captured after that point, re-verified via `curl` immediately before capture. Not
  a code defect; flagged here because a shared CI database being written by both automated
  tests and manual verification at the same time is a real collision risk worth the captain's
  awareness.

## Cleanup

Backend (port 8000) and frontend (port 3000) dev servers stopped by PID after the walk.
agent-browser session `s0-evidence` closed (not `close --all`). `sorento_crm_frontend/.env.local`
left in place (gitignored, verified via `git check-ignore`) for any follow-up verification.
