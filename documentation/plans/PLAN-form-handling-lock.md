# PLAN — Form "I'm handling this" handling-lock

**Status:** Phase 1 + 2 + 3 DONE. Full UAC verified, code review done + fixes applied. UNCOMMITTED, awaiting commit go-ahead.

### Phase 3 code review (2 reviewers, high effort) — resolved
- **REFUTED** (correctness #1, multi-active lock bypass): form entities never have >1 unresolved tracker — response+resolution are two clocks on ONE row; next-stage trackers spawn only after the prior resolves (sequential). Empirically 0 entities with >1 active. `.first()` on newest is safe.
- **FIXED**: (A) `_serialize` N+1 — hoisted per-request `flag_enabled` + `viewer_is_admin` out of the row loop. (B) `_assert_can_extend` now mirrors the CTA guard's admin-on-unclaimed allowance. (C) misleading "fail closed" comment corrected to fail-OPEN (deliberate). (D) claim/take-over/release responses now include viewer fields (shape parity with GET). (E-review) **Release now routes through an AlertDialog confirm** (per "confirm before detach" rule) — browser-verified.
- **Deferred (non-blocking, recommended follow-ups)**: guard as a `Depends(...)` factory instead of 15 imperative call-sites (altitude); dedupe the 2nd active-tracker GET by merging handling fields into the existing by-source serializer; `_user_name`/`_actor_is_admin` helper dedup. FE load-flicker left as-is (suppressing CTAs during load trades one cosmetic flicker for a worse common-path one; backend 403 makes it safe).
- Post-fix: BE pytest **102 passed**; FE vitest **44 passed** (_shared); tsc clean.

---

- **Phase 1** (FE prototype): UAC-verified in browser (P1-1/2/3/7/9 visual, rest vitest — 26 green).
- **Phase 2** (BE + FE off-mocks + tests): migration `269` (onto committed head `268`); BE pytest **79 green** (52 service/guard + 16 route + 7 notify/outbox + 4 settings/me); FE vitest **47 green** (_shared + settings). Contract enriched: GET form-sla-tracking returns `flag_enabled`/`viewer_eligible`/`viewer_is_admin`. Self-service channel toggles added (`notify_*_on_handling`).
- **Full UAC** (live Playwright + live API): F-1 claim→mine→release round-trip + take-over optimistic 409 ✓; F-2 flag-off regression ✓ (both directions); F-5 settings persist+gate ✓; F-3 (WhatsApp outbox success+fail) + F-4 (re-escalation reset) pytest-covered.
- Known: 3 pre-existing failures in `notification-channels-preference.test.tsx` (branch-level, proven unrelated — same failures with our edit stashed). Health-observability WIP parked in git stash.
- Branch `feat/form-handling-lock`. Uncommitted (awaiting review + user's commit go-ahead).
**Branch (proposed):** `feat/form-handling-lock`
**Slug:** form-handling-lock

---

## 1. Problem

When a form SLA tracker escalates, escalation **overwrites `assigned_to_id`** with a next-tier round-robin pick (`_escalate_tracker`, `form_sla_service.py:399`). But the business CTAs (approve/reject/process/close/submit/reopen) are gated by **status + permission only — NOT by assignee**. So after escalation, the *original* (failed) assignee AND the *new* escalation-tier assignee can both act. Two people work the same form → double work, conflicting decisions.

Applies to all four form types sharing `conversation_sla_tracking`: `complaint`, `stock_inquiry`, `purchase_request`, `sponsorship_form`.

## 2. Solution in one line

Once a form is **escalated** (`current_tier > 1`), all state-changing CTAs disable for everyone until an eligible team-chain member clicks **"I'm handling this"** — a lightweight, mutually-exclusive **handler lock** that is *separate from* the assignee. The lock holder is the only one who can act; anyone eligible can take over (with confirm) or the holder can release. The person who actually acts is recorded as `responded_by` / `resolved_by`, which may differ from `assigned_to_id`.

**This is NOT the existing `takeover()`/`reassign()`** (those switch the assignee). The handler lock never touches `assigned_to_id`, never changes tier, never de-escalates.

## 3. Premise corrections discovered during grilling

- **Extend already exists on all 4 forms** (shared `SlaExtendMenuItem` → `POST /conversation-sla-tracking/{id}/extend`, form-agnostic backend). No "add extend to the others" work. Only its *gating* changes (§6, decision 5a).
- **A takeover + cooldown-veto system already exists** (`ConversationSLATrackingService.takeover/reassign`, `SlaTakeoverService`, `sla_takeover_requests`). We reuse none of its assignee-switching semantics; the handler lock is a new, lighter concept. We DO mirror its notification/event-log patterns.

## 4. Locked decisions (the grill tree)

| # | Decision | Choice |
|---|---|---|
| Q1 | Assignee state after escalation | **Keep auto-assign** (round-robin pick stays `assigned_to_id`); CTAs lock behind an explicit claim. |
| — | What "I'm handling this" does | Sets a **separate handler field**; does **not** reassign, does **not** de-escalate, tier unchanged. `responded_by`/`resolved_by` = actual actor, may ≠ assignee. |
| Q2 | Who is eligible to claim | **Any member of the form's escalation team-chain** (`agent_id` + `team_set_code`, tiers 1→current). |
| — | Server-side lock | **Every CTA endpoint** checks `actor == handled_by_id` (or admin-on-unclaimed). UI hiding is cosmetic; the server check is the lock. |
| Q3 | Reverse / handover | **Release** (holder) + **direct Take-over-with-confirm** (any eligible). No timeout (design for inactivity auto-release later). No cooldown-veto. |
| Q4 | Which buttons the lock covers | **Only state-changing business CTAs** (approve/reject/process/close/submit/reopen). Comms/read/edit/delete stay on existing gates. |
| Q5a | Extend gating | **Handler-gated when escalated**; falls back to today's **assignee-only when not escalated**. |
| Q5b | Escalate (manual tier bump) | **Stays open** — permission-gated, NOT handler-gated (supervisor escape hatch). |
| Q5c | On re-escalation (tier N→N+1) | **Reset** — clear `handled_by_id`, everyone re-claims at new tier. |
| Q6 | Admin/superadmin bypass | **Bypass only when unclaimed.** If someone holds the lock, even admin must Take-over first (never silently collide an active handler). |
| Q7 | Notifications | Fire on claim / take-over / release. **Never notify the actor of their own action.** Channels honor per-user prefs; WhatsApp writes `integration_log` outbox on success AND fail. |
| Q8 | Feature flag | **Per-form-type** toggle in `system_settings` (`complaint` / `stock_inquiry` / `purchase_request` / `sponsorship_form`). Off = exact today's behavior, no code change to flip. |
| Q9 | WhatsApp templates | **Three use-case keys**: `sla_handling_claimed`, `sla_handling_taken_over`, `sla_handling_released` + new PARAM_VARIABLE `handler_name`. |

## 5. Guided state machine (UX)

Lock is **per active stage-tracker** and only bites while `current_tier > 1` on that tracker. A stage resolve spawns a fresh tier-1 tracker (`next_config_id`) → unlocked again.

| Viewer | Form state | CTAs | What they see |
|---|---|---|---|
| Eligible (team-chain) | escalated, unclaimed | disabled | Banner "Escalated to Tier N — no one handling yet" + primary **"I'm handling this"** |
| Eligible | I hold the lock | **enabled** | "You're handling this since HH:MM" + **Release** (in gear dropdown) + Extend/Escalate per 5a/5b |
| Eligible | someone else holds | disabled | "Jane is handling this since HH:MM" + **Take over handling** (confirm dialog) |
| Not eligible (page perm only) | escalated | disabled | Read-only "Escalated to Tier N, handled by Jane" — **no** claim button |
| Admin/superadmin | escalated, unclaimed | **enabled** | subtle "not yet claimed" hint, can act directly |
| Admin/superadmin | escalated, someone holds | disabled | must **Take over handling** first |
| Anyone | not escalated (tier 1) OR flag off | today's status+permission gates | no lock, no banner |

Labels: **"I'm handling this"** / **"Take over handling"** (primary buttons) / **"Release"** (gear dropdown). Distinct from the existing reassign-Takeover.

## 6. Notification matrix

Governing rule: **recipients = affected parties − the actor.**

| Event (actor X) | Notified (minus X) | Channels |
|---|---|---|
| First claim | Assignee (if ≠ X) + other eligible members | email / WA / in-app (per-user prefs) |
| Take-over (displaced D) | **Only** D | email / WA / in-app |
| Release | Eligible pool ("open again") | email / WA / in-app |

- In-app always fires (for recipients that pass the actor-exclusion). Email/WhatsApp gated by new per-user toggles.
- WhatsApp path is unchanged infra: producer sets `whatsapp_use_case` + `whatsapp_text` + `whatsapp_context_vars` in the notification `data`; worker `_send_whatsapp_for_notification` + `send_text_or_template` do the rest. In-window → raw text; out-of-window → admin-mapped approved template. **Outbox (`integration_log`) written on success AND failure** (existing behavior at `notification_tasks.py:176-237`).

## 7. Data model changes

**`conversation_sla_tracking`** (`app/models/sla.py:64`) — add:
- `handled_by_id` — FK `users.id`, `ondelete="SET NULL"`, nullable. The active handler lock. NULL = unclaimed.
- `handled_at` — timestamp, nullable. When the current lock was claimed.

**Event log** (`ConversationSLAEventLog`, `sla.py:176`) — new `event_type` values: `handling_claimed`, `handling_taken_over`, `handling_released`. Reuse `assigned_to_id` (the handler at the time), `triggered_by_id` (actor), `reason`.

**`users`** (`app/models/user.py`) — add per-event channel toggles:
- `notify_email_on_handling` (bool, default per existing convention)
- `notify_whatsapp_on_handling` (bool)
- ⚠️ Must be added to **both** `get_user`/`get_me` manual dict builders **and** `UserResponse` or they never reach the FE (known gotcha).

**`system_settings`** (singleton) — add per-form flag storage:
- `handling_lock_enabled_types` — JSON/CSV list of enabled `source_entity_type`s (extensible; one settings surface). Helper `is_handling_lock_enabled(db, source_entity_type) -> bool`.
- ⚠️ Add to **both** the settings GET dict **and** `SystemSettingUpdate` (singleton gotcha).

**WhatsApp use-cases** — add to `TEMPLATE_DEFAULT_USE_CASES` (`app/models/respond_template.py:37`): `sla_handling_claimed`, `sla_handling_taken_over`, `sla_handling_released`. Add `handler_name` to `PARAM_VARIABLES` (`respond_template_service.py:37`). No seeding — admin maps approved templates at runtime; out-of-window WA skips until mapped.

**Migration** — one Alembic revision for the tracker columns + user columns + system_settings column. `down_revision` chained onto the **committed** main head (verify via committed history, NOT `alembic heads` off disk — WIP-file gotcha). Backfill: none needed (`handled_by_id` NULL = unclaimed is correct for existing rows).

## 8. API contract

New endpoints (form-SLA scoped, under `app/api/v1/sla/form_sla_tracking.py`):

```
POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/claim
  → 200 { handled_by_id, handled_at, ... }
  Guard: flag on for this source_entity_type; tracker is form + escalated + unresolved;
         actor in team-chain; atomic UPDATE ... WHERE handled_by_id IS NULL (409 if already claimed).
  Side effects: event_log(handling_claimed); notify per matrix.

POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/take-over
  → 200 { handled_by_id (=actor), handled_at, previous_handler_id }
  Guard: same eligibility; conditional UPDATE ... WHERE handled_by_id = {expected_current}
         (body carries expected current holder for optimistic concurrency; 409 on mismatch).
  Side effects: event_log(handling_taken_over); notify displaced only.

POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/release
  → 200 { handled_by_id: null }
  Guard: actor == current handled_by_id (only holder releases). Admin may force-release? -> NO for v1;
         holder-only. (Admin can still Take-over then act.)
  Side effects: event_log(handling_released); notify eligible pool ("open again").
```

**CTA endpoint guard** (all business CTAs across the 4 forms — complaints.py, stock_inquiries.py, purchase_requests.py):
- New shared dependency/helper, e.g. `assert_can_act_on_form(db, source_entity_type, tracking, actor)`:
  - If flag off for type OR tracker not escalated → allow (today's behavior).
  - Else require `actor.id == tracking.handled_by_id` **OR** (actor is admin/superadmin AND `handled_by_id IS NULL`).
  - Else 403 with a clear message ("This form is being handled by <name>. Take over to act.").
- `responded_by`/`resolved_by` on the tracker + the business entity are set to `actor` (already the case; the guard guarantees actor == handler).

**Extend gating change** (`_assert_can_extend`, `sla_service.py:2336`): when the tracker is escalated AND flag on → require `actor == handled_by_id` instead of `actor == assigned_to_id`. Not escalated / flag off → unchanged (assignee-only).

**Feature-flag reads:** FE reads the per-form flags from settings to decide banner/gating; BE re-checks server-side (never trust FE). PR/SF share a FE component — gate on the **active tracker's `source_entity_type`**, not a hardcoded form name.

## 9. Loophole / invariant checklist

1. Server guard on **every** CTA (not just UI hide). ✔ §8
2. Atomic claim (`WHERE handled_by_id IS NULL`) — no double-claim race. ✔
3. Optimistic take-over (`WHERE handled_by_id = expected`) — no double take-over. ✔
4. Stale-tab race safe: displaced holder's next click 403s once lock moved. ✔
5. Scope boundary: **FORM SLA rows only** (`source_entity_type IN FORM_SLA_TYPES`). Never touch n8n conversation-SLA rows in the same table. ✔
6. Reset `handled_by_id` on each escalation; fresh unlocked tracker on stage resolve. ✔
7. Admin never silently collides an active handler (bypass only when unclaimed). ✔
8. Never notify the actor of their own action. ✔
9. WhatsApp outbox logged success + fail. ✔
10. New user columns in both dict builders; new setting in both builders. ✔

## 10. Three-phase breakdown

### Phase 1 — FE prototype (mock data)
- Shared `useHandlingLock(tracking)` hook + `HandlingLockBanner` + claim/release/take-over UI under `app/(protected)/sla-management/_shared/`.
- Wire into `ComplaintDetail.tsx`, `StockInquiryDetail.tsx`, `PurchaseRequestDetail.tsx` (SF via PR component). Gate the state-changing CTAs; Release in gear dropdown.
- Mock all 6 viewer states from §5 with stubbed hook returns. Screenshot each state.
- Document the API contract (§8) at top of `formSLAService.ts`.
- **No backend, no tests yet.** Verify states in Playwright MCP via sidebar → form detail.

### Phase 2 — BE wiring + tests
- Migration (§7). Models, `is_handling_lock_enabled`, notify producer (reuse `build_sla_whatsapp_data` + `create_with_channel_preferences`), 3 endpoints, CTA guard helper wired into all 4 forms' business routes, extend-gating change, escalation reset of `handled_by_id`, event-log types, use-case keys + `handler_name` variable.
- Settings UI: per-form flags (Settings → SLA or Forms). User notification settings: 2 new toggles.
- FE off mocks → real hooks/services.
- **Tests (land here, not deferred):**
  - pytest: claim/take-over/release happy + auth-denial + validation; CTA guard denies non-handler & allows handler & admin-on-unclaimed; escalation resets lock; extend gating; flag off = no lock; scope excludes conversation-SLA rows; notify actor-exclusion; WA outbox on success+fail.
  - vitest: `useHandlingLock` + banner across all 6 states; per-form gating; extend menu-item gating.
  - playwright: escalate a form → CTAs disabled → claim → CTAs enabled → second user take-over → first user's action 403s → release.
- Re-verify in Playwright MCP against live stack.

### Phase 3 — Code review
- `/code-review` (or ultra), address findings, then PR with Phase-1 screenshots + contract-match note.

## 11. Files touched (anticipated)

**BE:** `app/models/sla.py`, `app/models/user.py`, `app/models/respond_template.py`, `app/schemas/user.py`, `app/services/form_sla_service.py`, `app/services/sla_service.py`, `app/services/notification_service.py` (maybe), `app/services/respond_template_service.py`, `app/api/v1/sla/form_sla_tracking.py`, `app/api/v1/sla/sla_tracking.py`, `app/api/v1/complaints/complaints.py`, `app/api/v1/procurement/stock_inquiries.py`, `app/api/v1/procurement/purchase_requests.py`, `app/api/v1/user_management/settings.py`, new Alembic revision.

**FE:** `app/(protected)/sla-management/_shared/` (new hook + banner + actions), `SlaExtendAction.tsx`, `ComplaintDetail.tsx`, `StockInquiryDetail.tsx`, `PurchaseRequestDetail.tsx`, `formSLAService.ts`, settings page(s), user notification settings page.

## 12. UAC — User Acceptance Criteria (validate per phase; all pass before next phase)

TDD: write the failing test first (red) → implement (green) → refactor. Each phase gates on its UAC block. After all phases, run the **Full UAC** end-to-end via Playwright driving the live stack.

### Phase 1 UAC (FE prototype, mock data — vitest + Playwright MCP visual)
- **P1-1** Escalated + eligible + unclaimed → business CTAs disabled; banner "Escalated to Tier N — no one handling yet" + primary **"I'm handling this"** visible.
- **P1-2** Escalated + I hold → business CTAs **enabled**; "You're handling this since HH:MM"; **Release** in gear dropdown.
- **P1-3** Escalated + other holds → business CTAs disabled; "Jane is handling this since HH:MM" + **Take over handling**.
- **P1-4** Escalated + not eligible (page perm only) → CTAs disabled; read-only banner; **no** claim button.
- **P1-5** Escalated + admin + unclaimed → CTAs **enabled**; subtle "not yet claimed" hint.
- **P1-6** Escalated + admin + other holds → CTAs disabled; **Take over handling** required.
- **P1-7** (REGRESSION) Not escalated (tier 1) OR flag off → no banner; CTAs on existing status+permission gates; Extend/Escalate exactly as today.
- **P1-8** All 4 forms (complaint/SI/PR/SF) render banner+states via the shared component (SF via PR component, gated on active tracker's `source_entity_type`).
- **P1-9** Take-over shows a confirm dialog before firing.
- **P1-10** vitest green for the shared hook + banner across all 6 viewer states + regression state.

### Phase 2 UAC (BE wiring + FE off mocks — pytest + vitest)
- **P2-1** Migration adds the 3 column groups; `upgrade` + `downgrade` clean; single head chained off `268`.
- **P2-2** `POST /claim` eligible on escalated+unclaimed → 200, sets `handled_by_id`+`handled_at`, logs `handling_claimed`; concurrent second claim → **409** (atomic `WHERE handled_by_id IS NULL`).
- **P2-3** `POST /claim` non-eligible → 403; on non-escalated tracker → rejected; on flag-off form → rejected/no-op.
- **P2-4** `POST /take-over` eligible → 200 (`handled_by_id`=actor), logs `handling_taken_over`; optimistic mismatch → **409**.
- **P2-5** `POST /release` holder → 200 (`handled_by_id`=null), logs `handling_released`; non-holder → 403.
- **P2-6** Business CTA on escalated+flag-on: non-handler → **403**; handler → 200; admin-on-unclaimed → 200; admin when other holds → **403**.
- **P2-7** `responded_by`/`resolved_by` recorded = actor on the action (may ≠ `assigned_to_id`).
- **P2-8** Escalation (`_escalate_tracker`) resets `handled_by_id`→null (re-escalation clears lock).
- **P2-9** (REGRESSION) Extend: escalated+flag-on → handler-only (non-handler 403); not-escalated OR flag-off → assignee-only, unchanged.
- **P2-10** (REGRESSION) Escalate (manual): permission-gated, unchanged, works flag-on/off, NOT handler-gated.
- **P2-11** Notifications on claim/take-over/release per §6 matrix; **actor never notified**; email/WA gated by `notify_*_on_handling`; in-app always for non-actor recipients.
- **P2-12** WhatsApp uses `sla_handling_{claimed,taken_over,released}`; out-of-window → template, in-window → raw text; `integration_log` outbox written on success AND fail.
- **P2-13** (REGRESSION) Scope: claim/guard operate ONLY on form rows (`source_entity_type IN FORM_SLA_TYPES`); conversation-SLA rows untouched.
- **P2-14** New user toggles present in `get_user`/`get_me` AND `UserResponse`; new setting in settings GET dict AND `SystemSettingUpdate`.
- **P2-15** Per-form flag isolation: enabling `complaint` does not enable SI/PR/SF; flag off = today's behavior end-to-end.
- **P2-16** FE off mocks: real hooks/services hit the new endpoints; all states reflect live data.
- **P2-17** pytest green: happy + auth-deny + validation for each endpoint, guard matrix, scope, notify, both regressions.
- **P2-18** vitest green with real service shapes.

### Full UAC (end-to-end via Playwright driving live stack)
- **F-1** Enable flag for complaint → escalate a complaint → CTAs disabled + banner. User A claims → CTAs enabled. User B sees "A is handling" + Take over → B takes over (confirm) → A's next CTA **403s** → B acts. Release → open again. Resolve → `responded_by`/`resolved_by` = actual actor.
- **F-2** (REGRESSION) Flag off for PR → escalate PR → CTAs behave as today (no lock); Extend assignee-only; Escalate works.
- **F-3** A handling notification produces an `integration_log` outbox row (wrong creds → **failed** row still logged) — visible in Integration Logs.
- **F-4** Re-escalation (tier N→N+1) clears the lock — tier-2 handler must re-claim at tier 3.
- **F-5** Settings → per-form toggles persist and gate correctly across all 4 forms.

## 13. Open edge cases to confirm during build (not blockers)

- Inactivity auto-release (Q3 "design for B") — deferred to fast-follow; schema (`handled_at`) already supports it.
- "No resolvable WhatsApp contact" early-return currently skips integration_log (existing gap, `notification_tasks.py:134-138`) — out of scope, note only.
- Whether Release should be admin-force-able — v1 says holder-only; revisit if support asks.
