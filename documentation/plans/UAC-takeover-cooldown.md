# User Acceptance Criteria

**Scope:** PLAN-takeover-cooldown
**Status:** DESIGNED 2026-06-23 — pending implementation.

## Objective & how to read this

Every requirement is validated from **both ends** so we prove the behavior end-to-end, not just in
one layer:

- **BE-verify** — backend truth: pytest (service/endpoint), live-API against real postgres, and
  direct DB-row assertions (`sla_takeover_requests`, `conversation_sla_tracking`, notifications).
- **FE-verify** — frontend behavior: vitest (component/hook states) and Playwright MCP (drive via
  sidebar; assert DOM + `browser_network_requests` hit the right `/api/v1/*` call with the right
  payload, confirming the hook → service → api-client chain).

An AC **passes only when both lanes pass.** Where a lane is genuinely N/A (e.g. a pure scheduler
sweep has no direct user gesture), the FE lane asserts the resulting UI state after the BE event.

Format: Given / When / Then, then BE-verify + FE-verify. "SLA task" = a row in
`conversation_sla_tracking` (conversation or form). "Cooldown" = global
`system_settings.takeover_cooldown_seconds`. "Request" = a row in `sla_takeover_requests`. Unless
stated, cooldown = 60s and the contested task is assigned to a real owner.

---

## 1. Settings

### AC-CFG-1 — Cooldown configurable
- **Given** I am an admin on User Management → Settings (General)
- **When** I set "Takeover cooldown (seconds)" to `60` and save
- **Then** `system_settings.takeover_cooldown_seconds` persists `60` and subsequent takeovers use it.
- **BE-verify:** pytest PUT settings → row column == 60; reject negatives / non-int (422).
- **FE-verify:** vitest renders saved value in the field; Playwright edit→save→reload shows 60, and
  `browser_network_requests` shows the PUT to the settings endpoint with `takeover_cooldown_seconds`.

### AC-CFG-2 — Zero disables the cooldown (instant takeover)
- **Given** cooldown is `0`
- **When** any peer takes over a task
- **Then** it commits **instantly** — no pending request, no countdown; assignee flips, RR cursor
  advances, event log + Respond push + notify all fire (pre-feature behavior).
- **BE-verify:** pytest initiate with cooldown 0 → returns committed tracking, **no** `sla_takeover_requests`
  row, `assigned_to_id`==initiator, `reassignment/takeover` event log present.
- **FE-verify:** Playwright Takeover→Confirm with cooldown 0 → row immediately leaves My Team / lands
  in My Pending; **no** countdown bar ever renders; vitest: hook returns committed shape → no bar branch.

### AC-CFG-3 — Default 60 on fresh install
- **Given** a freshly migrated `system_settings` row
- **Then** `takeover_cooldown_seconds` defaults to `60`.
- **BE-verify:** migration test + model default/server_default == 60.
- **FE-verify:** settings field shows 60 on an unconfigured tenant (vitest with default fixture).

---

## 2. Initiate

### AC-INIT-1 — Pending request created (cooldown > 0)
- **When** Bob clicks Takeover → Confirm on Jayson's CMP-0010
- **Then** a `pending` request is created (`initiator=Bob`, `contested_assignee_id=Jayson`,
  `commit_at≈now+60s`); **`assigned_to_id` UNCHANGED (Jayson)**; response carries `{request_id, commit_at}`.
- **BE-verify:** pytest/live-API: request row asserted; tracking assignee/tier/clocks unchanged;
  response body shape validated.
- **FE-verify:** Playwright: Confirm → POST `/{tracking_id}/takeover`; row shows depleting bar +
  Cancel; vitest: hook stores `commit_at`, bar mounts.

### AC-INIT-2 — Nothing moves during cooldown
- **Then** assignee, tier, team_set_code, agent_id, all clocks remain the owner's before `commit_at`.
- **BE-verify:** DB snapshot of tracking before vs during cooldown — byte-identical on those columns.
- **FE-verify:** Jayson's My Pending still lists the task as his (Playwright/vitest), not moved to Bob.

### AC-INIT-3 — Unassigned task commits instantly
- **Given** team task with `assigned_to_id` NULL, cooldown 60s
- **Then** takeover commits **immediately** (no pending request).
- **BE-verify:** pytest: no request row, instant flip.
- **FE-verify:** Playwright: no bar; row moves at once.

### AC-INIT-4 — FCFS lock (one pending per task)
- **Given** Bob's takeover is pending on CMP-0010
- **When** Alice clicks Takeover on the same task
- **Then** API returns **409 with Bob's existing request**; no second pending row; Alice's UI shows
  "pending · Bob · m:ss", buttons disabled.
- **BE-verify:** pytest: partial-unique enforced; second initiate → 409 carrying existing request;
  exactly one pending row.
- **FE-verify:** vitest: 409 path renders disabled "pending · Bob" state (not an error toast);
  Playwright two-session race asserts the second user sees the running bar, disabled buttons.

### AC-INIT-5 — Cannot take over a resolved task
- **Given** CMP-0010 resolved
- **Then** Takeover rejected (validation error); no request row.
- **BE-verify:** pytest: resolved → validation error, no row.
- **FE-verify:** vitest: error toast surfaced via `extractApiError`; resolved rows don't show Takeover.

---

## 3. Cancel (initiator)

### AC-CANCEL-1 — Initiator cancels
- **When** Bob clicks Cancel
- **Then** request → `cancelled` (`resolved_by=Bob`, `reason='cancel'`); assignment unchanged; **Jayson
  notified in-app only**.
- **BE-verify:** pytest: status/reason set; assignment untouched; exactly one in-app notification,
  **no** email/WhatsApp queued regardless of toggles.
- **FE-verify:** Playwright: Cancel → POST `/takeover-requests/{id}/cancel`; bar disappears, Takeover
  button returns; vitest loading/success/error states.

### AC-CANCEL-2 — Admin can cancel
- **Then** an admin/superadmin cancels successfully.
- **BE-verify:** pytest with admin principal → 200.
- **FE-verify:** Playwright as admin → cancel works on someone else's pending request.

### AC-CANCEL-3 — Stranger cannot cancel
- **When** an unrelated non-admin calls cancel
- **Then** denied (403/404); request stays pending.
- **BE-verify:** pytest: denied; row unchanged.
- **FE-verify:** stranger never sees a Cancel control (not their request); direct API call denied.

---

## 4. Reject (original assignee)

### AC-REJECT-1 — Owner rejects
- **When** Jayson clicks Reject
- **Then** request → `rejected` (`resolved_by=Jayson`, `reason='reject'`); stays Jayson's; **Bob
  notified** (in-app + assignment toggles): "Jayson kept the task".
- **BE-verify:** pytest: status/reason; assignment unchanged; Bob notification with correct channels.
- **FE-verify:** Playwright: Reject from banner/inline → POST `/reject`; banner clears; vitest states.

### AC-REJECT-2 — Admin can reject
- **BE-verify:** pytest admin → 200. **FE-verify:** Playwright admin rejects.

### AC-REJECT-3 — Non-owner stranger cannot reject
- **When** a non-admin who is not the contested assignee calls reject
- **Then** denied; request stays pending.
- **BE-verify:** pytest denied (snapshot `contested_assignee_id` is the gate).
- **FE-verify:** stranger has no Reject affordance; direct API call denied.

---

## 5. Implicit veto (owner terminal actions)

### AC-VOID-1 — Owner resolves → void
- **When** Jayson resolves during cooldown
- **Then** request → `voided` (`reason='resolved'`); no commit; **Bob notified** "resolved by Jayson".
- **BE-verify:** pytest: resolve path actively voids; sweep later finds nothing to commit; Bob notified.
- **FE-verify:** Playwright: Jayson resolves → Bob's bar flips to "cancelled: resolved" on next poll;
  vitest renders voided state.

### AC-VOID-2 — Owner reassigns away → void
- **When** Jayson reassigns to Carol
- **Then** request voids (`reason='reassigned'`); Bob notified; task is Carol's.
- **BE-verify:** pytest: reassign actively voids; assignee==Carol.
- **FE-verify:** Playwright reassign → Bob's bar voids; row now shows Carol.

### AC-VOID-3 — Auto-escalation wins → void
- **Given** SLA breaches mid-cooldown
- **Then** escalation proceeds (never blocked); request voids (`reason='escalated'`); Bob notified.
- **BE-verify:** pytest: escalation scheduler path voids any pending request; tier/owner changed by
  escalation as normal.
- **FE-verify:** Playwright (or vitest with forced escalation): Bob's bar voids; task reflects new tier.

### AC-VOID-4 — Third-party Reassign blocked while pending
- **When** another member tries Reassign on a pending-takeover row
- **Then** blocked ("takeover pending"); request unaffected.
- **BE-verify:** pytest: reassign by third party on a pending tracking → validation error; row intact.
- **FE-verify:** vitest/Playwright: Reassign control disabled/blocked on a pending row with a reason.

---

## 6. Commit (scheduler sweep)

### AC-COMMIT-1 — Unchallenged → committed
- **Given** `commit_at` passed unchallenged
- **When** the `takeover_request_commit` sweep runs
- **Then** commit uses existing reassignment logic: assignee→Bob, **tier/team/agent re-derived from
  Bob's standing at commit**, RR cursor advanced, `reassignment/takeover` event log, Respond push
  (conversation rows); request → `committed`; **both** Jayson and Bob notified.
- **BE-verify:** pytest: run sweep handler directly → assert assignee, re-derived tier, cursor, event
  log, request status, both notifications; live-API end-to-end on real postgres.
- **FE-verify:** Playwright: let timer ride → at zero "Finalizing…" → row moves from Jayson's My
  Pending into Bob's My Pending after poll; vitest "Finalizing" branch.

### AC-COMMIT-2 — Commit within one tick of deadline
- **Then** reassigned within ~one scheduler tick (≤ ~15s) of `commit_at`.
- **BE-verify:** pytest with a `commit_at` in the past → single sweep commits it; timing asserted via
  injected clock, not wall-sleep.
- **FE-verify:** Playwright: "Finalizing…" resolves to committed within the poll window.

### AC-COMMIT-3 — Re-validate: resolved before commit
- **Given** task resolved after `commit_at` but before the sweep
- **Then** no flip; request → `voided`; Bob notified.
- **BE-verify:** pytest: seed pending+resolved → sweep voids, assignment untouched.
- **FE-verify:** Bob's UI shows voided, never shows him as owner.

### AC-COMMIT-4 — Re-validate: owner changed before commit
- **Given** `assigned_to_id` != `contested_assignee_id` at sweep time
- **Then** voids (no flip); Bob notified.
- **BE-verify:** pytest snapshot-mismatch → void.
- **FE-verify:** Bob's UI voids.

### AC-COMMIT-5 — Re-validate: initiator ineligible
- **Given** initiator no longer eligible (removed from teams / no standing)
- **Then** voids (`reason='ineligible'`); assignment unchanged.
- **BE-verify:** pytest: strip Bob's membership → sweep voids.
- **FE-verify:** N/A gesture; assert Bob's UI shows voided/ineligible message.

### AC-COMMIT-6 — `commit_at` frozen against mid-flight setting change
- **When** admin changes global cooldown during a pending window
- **Then** `commit_at` stays `T`.
- **BE-verify:** pytest: change setting after create → request `commit_at` unchanged.
- **FE-verify:** running bar duration does not jump when the setting changes elsewhere.

### AC-COMMIT-7 — Sweep task seeded for live
- **Given** a freshly migrated DB
- **Then** `scheduled_tasks` row `takeover_request_commit` exists (data migration), idempotent on re-run.
- **BE-verify:** migration test: row present; downgrade/upgrade or double-run → no duplicate.
- **FE-verify:** appears in System Management → Scheduled Tasks list (Playwright via sidebar).

---

## 7. Notifications & channels

### AC-NOTIF-1 — Start notification to owner with deep link
- **Then** Jayson gets in-app (always) + email/WhatsApp per HIS assignment toggles; message links to
  `/?takeover=<tracking_id>`.
- **BE-verify:** pytest: notification rows created with correct channels; link contains the tracking id.
- **FE-verify:** vitest renders the in-app entry; Playwright clicking the link routes to `/?takeover=`.

### AC-NOTIF-2 — Channel gating honored
- **Given** Jayson `email_on_assignment=false`, `whatsapp_on_assignment=true`
- **Then** no email; WhatsApp sent (if RespondContact linked); in-app still appears.
- **BE-verify:** pytest matrix: each toggle combination → exact channels queued; integration_log
  written for the Respond send (success AND failure).
- **FE-verify:** in-app always visible regardless of email/WhatsApp toggles.

### AC-NOTIF-3 — Cancel is in-app only
- **BE-verify:** pytest: cancel → in-app only, no email/WhatsApp even with toggles on.
- **FE-verify:** Jayson sees only the in-app entry.

### AC-NOTIF-4 — Reject/commit/void use assignment toggles
- **BE-verify:** pytest: each event → in-app always + email/WhatsApp per recipient toggles.
- **FE-verify:** recipients' in-app entries appear for each event.

### AC-NOTIF-5 — Both SLA types covered; Respond push skipped for form rows
- **Given** a **form** SLA task
- **Then** cooldown/notify/commit all work; **Respond push skipped** (no Respond conversation).
- **BE-verify:** pytest with a form row: commit succeeds, no Respond call attempted.
- **FE-verify:** form-SLA task shows the same bar/banner/controls as conversation rows.

---

## 8. Deep link & banner (original assignee)

### AC-LINK-1 — Param survives login
- **Given** Jayson logged out, clicks `/?takeover=<id>`
- **Then** after signin he lands on `/?takeover=<id>` (callbackUrl carries `pathname+search`).
- **BE-verify:** N/A (NextAuth/layout); assert callbackUrl construction in a unit test if feasible.
- **FE-verify:** Playwright logged-out → link → signin → back to `/?takeover=<id>`.

### AC-LINK-2 — Pin-fetch banner regardless of pagination
- **Given** the task would be on page 3
- **Then** it's fetched by id and shown in a **flashing banner pinned at top** with bar + Reject.
- **BE-verify:** single-row `GET /conversation-sla-tracking/{id}` returns the row with takeover state.
- **FE-verify:** Playwright with >1 page of My Pending: open link → banner shows the row at top
  (not via list scroll); `browser_network_requests` shows the by-id fetch; vitest loading/empty/data.

### AC-LINK-3 — Param cleared after action
- **When** Jayson rejects/dismisses
- **Then** `?takeover=` stripped once (idempotent).
- **FE-verify:** Playwright: URL no longer has the param after action; double-trigger safe (vitest).

### AC-LINK-4 — Terminal state in banner
- **Given** already committed/cancelled/voided when opened
- **Then** banner shows terminal state, no live bar, no Reject.
- **BE-verify:** by-id endpoint returns terminal request status.
- **FE-verify:** vitest renders each terminal variant; Playwright open-after-commit shows "already
  taken over".

### AC-LINK-5 — Organic inline indicator
- **Given** Jayson browses My Pending without the link
- **Then** the contested row shows inline "Being taken over · m:ss · Reject".
- **FE-verify:** vitest: row with pending takeover renders inline indicator + Reject; Playwright reject
  from inline works without the deep link.

---

## 9. Countdown UI

### AC-UI-1 — Bar driven by server time, survives refresh
- **Then** bar reflects `commit_at - now`, animates locally, re-syncs after refresh/refetch (no jump/loss).
- **BE-verify:** responses always include absolute `commit_at`.
- **FE-verify:** vitest: bar computes from `commit_at`, not a local counter; Playwright refresh
  mid-cooldown → bar resumes at correct remaining time.

### AC-UI-2 — Finalizing at zero
- **When** bar hits 0:00 before the sweep commits
- **Then** UI shows "Finalizing…" and polls until `committed`, then the row moves.
- **FE-verify:** vitest "Finalizing" branch when `now>commit_at` && status still pending; Playwright
  observes Finalizing→committed transition.

### AC-UI-3 — Initiator vs observer controls
- **Then** initiator row: bar + Cancel (Reassign hidden); other members: "pending · Bob · m:ss",
  buttons disabled.
- **FE-verify:** vitest both variants by viewer identity; Playwright two sessions confirm divergent UI.

### AC-UI-4 — Polling scoped to pending
- **Then** widget polls (~5–10s) only while a pending takeover is visible; stops otherwise.
- **FE-verify:** vitest: `refetchInterval` enabled only when pending present; Playwright network log
  shows polling starts on pending and stops after commit/cancel/reject.

---

## 10. Audit

### AC-AUDIT-1 — All terminal requests retained
- **Given** multiple attempts over time (committed/rejected/cancelled/voided)
- **Then** every request row persists; only a second **pending** row is blocked; history queryable.
- **BE-verify:** pytest: create→resolve cycles leave N terminal rows; partial-unique blocks only a
  second pending; query returns full lifecycle with actors/reasons/timestamps.
- **FE-verify:** N/A (no UI list this phase); assert via API that history is retrievable for future
  audit surfacing.
