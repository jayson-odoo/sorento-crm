# PLAN - Form SLA Undo (grace-window deferral + post-grace reversal)

> Status: **S0-S9 DONE 2026-08-11** on branch `feat/form-sla-undo`, verified end to end against
> the real stack. All 13 actions registered and invertible; grace configurable per stage and
> globally; audit on all five paths.
> **S9 (2026-08-11): scaled beyond PR/SF.** Review pass closed four holes (void_tracker now
> writes a `voided`/`reopened` event log; undo refused while a NEW action is pending
> (`action_pending`); SI/CX runner kwargs completed incl. `StockInquiryUpdate` rehydration;
> scheduler no longer lets a handler-less process eat a task's tick - see
> `tests/test_scheduled_task_unhandled_tick.py`, 47% of ticks were being eaten by worktree
> workers). Shared `dispatch_or_defer` (`form_action_dispatch.py`) now wired into stock-inquiry
> (update-and-reply / PS-approve / PS-reject / purchasing-reject), complaint (approve / reject /
> process / close) and ticket (resolution update-and-reply) routes; FE banner + undo mounted on
> StockInquiryDetail, ComplaintDetail and the ticket detail page. SI flow browser-verified:
> 202 -> sweep commit -> post-grace undo (tracker voided+reopened, contact correction in outbox).
> Sequenced ahead of `PLAN-permission-gating.md` by the user's call. Contract:
> `UAC-form-sla-undo.md`.
>
> Shipped: `sla_form_actions` (migration 312a) + seeded sweep task (312b), `FormActionService`,
> `form_action_registry` / `form_actions` (action #3), `form_action_grace`, `form_action_undo`
> (guardrail + void + reopen), `form_action_notify`, four routes, FE `useFormAction` +
> `FormActionBanner` + `UndoActionDialog` off mocks.
>
> Tests: 21 pytest, 13 vitest, 1 playwright spec (`e2e/form-sla-undo.spec.ts`). Full-suite name
> diff vs a stashed tree: zero new failures (37 pre-existing, identical both sides).
>
> Three registry-integrity tests exist because six of the thirteen runners were written with
> kwargs the real methods do not accept. Introspection caught them; the checks now run in CI so
> a wrapped method cannot drift from its declaration silently.
>
> Dev DB carries `grace_seconds = 10` on purchase_request / project_sales_manager. Every other
> stage is NULL and the global default is 0, so nothing else defers.
> Prior art to mirror, not reinvent: `PLAN-takeover-cooldown.md`, `sla_takeover_service.py`,
> `SlaTakeoverRequest`, `TakeoverCountdown.tsx`, `_handler_takeover_request_commit`.

## The shape of the problem

One click on Approve fires six things (`procurement_service._apply_approval_decision`, line 7226):
status + approval_status write, requester email, **Respond.io WhatsApp to the contact**, form-SLA
event (which resolves the approver stage and spawns + assigns + notifies the CS stage), and the
approval automation dispatch.

The WhatsApp is why this is a deferral feature and not an undo feature. You cannot unsend it. The
only way a ten-second undo is genuinely free is if the click **does nothing at all** until the
window closes. That is the design.

Post-grace undo is a different mechanism with a different promise: not "nothing happened" but
"we reversed it and told everyone".

## Scope - what is actually deferrable

12 active `form_sla_configs` rows produce 20 (form, resolve-event) pairs. Two corrections found
while surveying:

- `workflow_submission` carries an active config but **nothing in the codebase emits a form-SLA
  event for it and it has zero trackers**. The row exists only to stop a response-validation 500
  (see the comment in `FORM_SLA_TYPES`). Its two pairs are excluded. Real scope: **18 pairs**.
- PR and SF share `PurchaseRequestHeader` and most service methods, so 18 pairs collapse to
  **13 distinct service actions**.

| # | Action key | Entity types | Service method | Resolve event(s) | Spawns next stage |
|---|---|---|---|---|---|
| 1 | `pr.send_for_approval` | purchase_request, sponsorship_form | `set_pending_approval` | send_for_approval | no |
| 2 | `pr.reject_submitted` | purchase_request, sponsorship_form | `reject_submitted` | reject_submitted | no |
| 3 | `pr.approval_decision` | purchase_request, sponsorship_form | `_apply_approval_decision` | approved / approval_rejected | **yes (CS)** |
| 4 | `pr.finalize` | purchase_request, sponsorship_form | `_finalize_request` | resolved | no |
| 5 | `pr.void` | purchase_request, sponsorship_form | `void_request` | voided | no |
| 6 | `si.project_sales_approve` | stock_inquiry | `project_sales_approve_inquiry` | project_sales_approve | **yes (purchasing)** |
| 7 | `si.project_sales_reject` | stock_inquiry | `project_sales_reject_inquiry` | project_sales_reject | no |
| 8 | `si.purchasing_decide` | stock_inquiry | `purchasing_reject_inquiry` | purchasing_decide | no |
| 9 | `si.purchasing_respond` | stock_inquiry | `update_inquiry_and_reply` | purchasing_respond | no |
| 10 | `si.void` | stock_inquiry | `void_inquiry` | voided | no |
| 11 | `cx.decide` | complaint | `decide_complaint` | approved / rejected / settled_on_site | **yes (CS) on approved** |
| 12 | `cx.finalize` | complaint | `_finalize_complaint` | resolved | no |
| 13 | `tk.resolve` | ticket | `update_resolution_and_reply` | resolved | no |

The four that spawn a next stage are the ones the incident is about and the ones where undo has
real work to do. The rest are state-only reversals.

### Where undo is honest and where it is not

Name this now rather than discover it in review:

- **#3, #6, #11** - clean. Reversal is state + void spawned tracker + reopen prior tracker.
- **#9, #13** - the action's whole point is a message to the contact. Post-grace undo cannot recall
  it. Reversal is state-only plus a correction message. The Undo dialog must say so.
- **#4, #12** - **invertible after all.** The first draft of this plan claimed PDF generation and
  approval automation hang off finalize. Reading `_finalize_request` (procurement_service.py:4853)
  and `_finalize_complaint` (complaints_service.py:2226) shows they do exactly three things:
  (a) set the lifecycle status plus `resolved_at`/`resolved_by`, (b) send a Respond.io
  status-update message, (c) emit the `resolved` SLA event closing the CS stage.
  `_dispatch_approval_automation` hangs off the **approval decision**, not finalize.
  The inverse is: restore the captured status and clear the resolved stamps, reopen the CS tracker,
  send a correction. Nothing to void - finalize spawns no next stage.
  One real interaction: finalize moves a complaint out of the auto-linker's
  `LINKABLE_STATUSES` (`processed_by_cs`, `fulfilled`). Undo returns it to a linkable status; the
  linker picks it up on the next order-side change and the undo does not retro-link (AC-PGE-8).
- **#5, #10** - void is already a reversal-shaped action. Undoing a void = un-voiding. Low risk.

## Architecture

### One registry, two handler kinds

`app/services/form_action_registry.py`

```python
@dataclass(frozen=True)
class FormAction:
    key: str                      # "pr.approval_decision"
    entity_types: tuple[str, ...]
    execute: Callable             # (db, payload) -> None   runs the real service method
    capture: Callable             # (db, payload) -> dict   prior state, BEFORE execute
    invert: Callable | None       # (db, record) -> None    None = not undoable post-grace
    resolve_event: Callable       # (payload) -> str        which event this will emit
    tells_contact: bool           # drives AC-N-5
```

`execute` calls the **existing** service method unchanged. This is the single most important
constraint in the plan: the deferred path and the immediate path must be the same code, or
AC-D-4 is unmeetable and the two paths drift within a release.

`capture` snapshots the exact domain fields the action will overwrite, before it runs, into
`prior_state_json`. The inverse restores from that snapshot - never from a guessed default
(AC-PGE-1).

### One table

`sla_form_actions` - mirrors `SlaTakeoverRequest`'s lifecycle vocabulary deliberately.

| column | notes |
|---|---|
| `id` | uuid pk |
| `action_key` | registry key |
| `source_entity_type` / `source_entity_id` | the form |
| `event_name` | resolved resolve-event, for the guardrail |
| `payload_json` | args for `execute` |
| `prior_state_json` | from `capture` |
| `requested_by_id` | FK users |
| `channel` | `ui` / `immediate` - only `ui` ever defers |
| `status` | `pending` / `committed` / `cancelled` / `ineligible` / `failed` / `undone` |
| `commit_at` | naive UTC |
| `committed_at`, `resolved_at`, `resolution_reason`, `error_text` | |
| `spawned_tracking_id` | the next-stage tracker created at commit, for the void |
| `prior_tracking_id` | the stage tracker resolved by this action, for the reopen |
| `undone_by_id`, `undone_at`, `undo_reason` | post-grace |

Indexes: partial unique on `(source_entity_type, source_entity_id) WHERE status='pending'`
(AC-D-7); `(status, commit_at)` for the sweep; `(source_entity_type, source_entity_id,
committed_at DESC)` for "last committed action".

Committed rows are the undo history. Nothing is deleted (AC-A-4).

### One service

`app/services/form_action_service.py`

- `dispatch(action_key, entity_type, entity_id, payload, actor_id, channel)` - the only entry
  point routes call. Resolves grace; `0` or non-`ui` channel -> `capture` + `execute` now and
  write a `committed` row (so history exists for post-grace undo even on the immediate path);
  otherwise write `pending` and return.
- `commit_due()` - sweep, mirrors `SlaTakeoverService.commit_due`.
- `commit_one(row)` - re-validates premise (AC-D-8), transitions `pending -> committed`
  conditionally (`UPDATE ... WHERE status='pending'` with rowcount check) for idempotency
  (AC-D-6), then executes.
- `cancel(row_id, actor)` - in-grace.
- `undo(entity_type, entity_id, actor, reason)` - post-grace.
- `eligibility(entity_type, entity_id, viewer)` - the read behind AC-PG-6.

`app/services/form_action_guard.py` - the guardrail (AC-PG-2/3), used by both the read and the
execute so they cannot disagree.

### Grace resolution

`form_sla_configs.grace_seconds` (nullable int) -> `system_settings.form_sla_grace_seconds`
(int, default `0`). Default `0` means **deploying this changes no behaviour** until someone turns
it on. Both columns must land in the manual GET dict builders **and** the update schemas, per the
`get_user` / `system_settings` drop-fields rule.

### Scheduler

Register `form_action_commit` alongside `takeover_request_commit` in
`app/scheduler/task_scheduler.py`. The dispatcher already ticks at 10s. A 10s grace with a 10s
tick means real commit lands within ~20s; the lazy-commit-on-read path (AC-D-5) hides that for
anyone looking at the form, which is everyone who cares.

### Reopen mechanics

`prior_tracking_id` is reopened by clearing `is_resolved` / `resolved_by`, restoring the assignee,
and restarting the clock from now against the stage's own hours via the existing working-hours
helper (`_working_due_naive`). `escalated_at` is left as it was, so an escalated stage returns
escalated and stays locked (AC-PGE-4) - the handling-lock rule keys on `escalated_at`, never on
tier. Breach history stays in the event logs, which survive because they are FK'd by tracking id.

## API contract

Documented here so the S1 frontend mock can be built against it before any backend exists, per the
three-phase loop. If a deviation proves unavoidable in S2, update this section in the same PR.

### The existing domain routes keep their URLs

Approve stays `POST /api/v1/procurement/purchase-requests/{id}/approval`, and so on for all 13.
Deferral happens inside, so no route moves and no caller re-points. What changes is the response
when the action defers:

```jsonc
// 202 Accepted - deferred (in-system UI caller, resolved grace > 0)
{
  "deferred": true,
  "pending_action_id": "uuid",
  "action_key": "pr.approval_decision",
  "commit_at": "2026-08-10T09:31:12",      // naive UTC, as the tracking columns are
  "window_seconds": 10                      // fixed denominator for the countdown bar
}
```

`200` with today's exact body when it does not defer (grace `0`, or a portal / `X-API-Key` / n8n /
MCP caller). **No existing response shape changes** - AC-D-2, AC-D-3.

### New endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/sla/form-actions/current` | `?entity_type=&entity_id=` - the pending action for a form, or `null`. Drives the countdown across refresh (AC-U-3) and performs the lazy commit (AC-D-5). |
| `POST` | `/api/v1/sla/form-actions/{id}/cancel` | In-grace undo. Actor or admin only, no permission slug (AC-IG-1/2). `409` if already committed (AC-IG-3). |
| `POST` | `/api/v1/sla/form-actions/undo` | Post-grace. Body `{entity_type, entity_id, reason}`. Requires the permission slug; `422` on an empty reason; `409` on a race. |

`GET .../current` response:

```jsonc
{
  "pending": {
    "id": "uuid", "action_key": "pr.approval_decision",
    "requested_by_id": "uuid", "requested_by_name": "Sabrina",
    "commit_at": "...", "window_seconds": 10,
    "can_cancel": true                       // viewer-relative, mirrors takeover's serialize()
  } | null,
  "last_outcome": { "status": "ineligible" | "failed", "reason": "..." } | null
}
```

`last_outcome` is how the FE renders the two states it cannot predict (AC-U-4): the action was
voided as ineligible, or it failed. It is cleared once the client has seen it.

### Eligibility rides on the form detail response

Per AC-PG-6 the FE never guesses. Every form detail endpoint in `FORM_SLA_TYPES` gains:

```jsonc
"undo": {
  "can_undo": false,
  "action_key": "pr.approval_decision",
  "action_label": "Approval",
  "committed_at": "...",
  "blocked_reason": "next_stage_acted",     // machine-readable
  "blocked_by_name": "Farah",
  "blocked_at": "2026-08-10T14:32:00",
  "tells_contact": true                      // dialog warns the correction goes to the customer
}
```

`blocked_reason` values: `no_action`, `next_stage_acted`, `status_moved`, `not_invertible`,
`no_permission`. The FE maps them to copy; the server owns the truth and re-checks at execute time
(AC-PG-7).

**Watch the `response_model` trap.** These are new fields on existing responses - if the route
declares a `response_model` that does not list them, FastAPI strips them silently and the FE sees
nothing. Add them to the schema, and assert the contract in a test.

## What each action captures and restores

The rule: **`capture` snapshots exactly the columns the method writes, read before it runs.**
`invert` writes those values back. Never a default, never a guess (AC-PGE-1).

Verified by reading the methods:

| # | Action | Captured columns |
|---|---|---|
| 3 | `pr.approval_decision` | `approval_status`, `status`, `approved_at`, `approved_by`, `rejected_by_id`, `approval_signature_ref`, `approval_comments` |
| 4 | `pr.finalize` | `status`, `resolved_at`, `resolved_by` |
| 6 | `si.project_sales_approve` | `status`, `rejection_reason`, `rejected_at`, `rejected_by`, `rejected_from` |
| 12 | `cx.finalize` | `status`, `resolved_at`, `resolved_by` |

The other nine are enumerated the same way in S6, by reading each method rather than by pattern-
matching its name. Every capture list is a review artifact: a reviewer should be able to diff the
captured columns against the columns the method assigns and find them identical.

Beyond columns, every capture also records `prior_tracking_id` (the stage tracker this action will
resolve) so the reopen has a target, and commit records `spawned_tracking_id` if a next stage was
created.

## Migration

One migration, four things:

```sql
CREATE TABLE sla_form_actions (...);                       -- columns as tabled above
CREATE UNIQUE INDEX ux_sla_form_actions_one_pending
  ON sla_form_actions (source_entity_type, source_entity_id)
  WHERE status = 'pending';
CREATE INDEX ix_sla_form_actions_sweep ON sla_form_actions (status, commit_at);
CREATE INDEX ix_sla_form_actions_last  ON sla_form_actions (source_entity_type, source_entity_id, committed_at DESC);

ALTER TABLE form_sla_configs ADD COLUMN grace_seconds INTEGER NULL;
ALTER TABLE system_settings  ADD COLUMN form_sla_grace_seconds INTEGER NOT NULL DEFAULT 0;
```

Plus the permission row `sla_management.form_sla.undo_action` in `permission_registry.py`.

Check `alembic heads` on the real filesystem before setting `down_revision` - a committed head is
not necessarily the latest one on this branch.

## Blocking edits while pending (AC-D-10)

Enforced in one place, not per route: a `assert_no_pending_action(db, entity_type, entity_id)`
guard called by the same service methods that already call
`handling_lock_service.assert_can_act_on_form`. That helper is already the chokepoint for "may this
person touch this form right now", so the pending check belongs beside it rather than in a new
layer. `409` with the pending action id so the FE can show the countdown instead of a bare error.

## Frontend surface

| File | Change |
|---|---|
| `sla-management/_shared/FormActionCountdown.tsx` | New. Wraps the existing `TakeoverCountdown` presentation; denominator from `window_seconds`, never a client-side start time. |
| `sla-management/_shared/useFormAction.ts` | New. Polls `GET .../current` while pending, exposes `cancel()`, `refresh()`. |
| `sla-management/_shared/UndoActionDialog.tsx` | New. `AlertDialog`, mandatory reason, consequence list built from `action_key` + `tells_contact`. |
| `sla-management/_shared/formSLAService.ts` | Add the three calls. |
| PR/SF, complaint, stock-inquiry, ticket detail pages | Render the countdown, disable other CTAs while pending, add Undo to the actions menu gated on the eligibility block. |

The lock banner and the SLA banner are already two separate queries that must both be invalidated
after a state change - the same trap applies here. Cancelling or undoing must invalidate
`form-handling-tracker` **and** `form-sla-trackers`, not just its own key, or one banner lags a
reload.

## Slices

Each slice follows the three-phase loop: FE mock first, then BE + tests, then review.

- **S1 - FE prototype (FIRST, per PRINCIPLES phase 1).** Countdown bar on the SF/PR detail page +
  actions-menu Undo + confirm dialog, against mocked hooks and the contract above. All nine UI
  states from AC-U-7. Screenshot the golden path and the blocked-with-reason case.
  **No backend code in this slice.**
- **S0 - foundation, no behaviour change.** Migration (table + two grace columns), permission row,
  registry skeleton, `FormActionService` with only the immediate path, settings wired through both
  dict builders. Every action still fires instantly because default grace is `0`.
  Tests: dispatch-immediate produces identical side effects to calling the method directly.
- **S2 - deferral for action #3.** Route interception for `_apply_approval_decision`, sweep
  handler, lazy commit, cancel endpoint, `409`/`ineligible`/`failed` paths. FE off mocks.
  This alone closes the incident that started this.
- **S3 - guardrail + eligibility read.** `can_undo` on the form detail response, refusal reasons.
- **S4 - post-grace undo for #3.** Inverse, void spawned tracker, reopen prior tracker, permission
  slug `sla_management.form_sla.undo_action`, mandatory reason.
- **S5 - notification.** Reopened assignee, voided assignee, contact correction through the
  existing structured update template, outbox logging on both outcomes.
- **S6 - registry extension.** The remaining 12 actions (#1, #2, #4, #5, #6, #7, #8, #9, #10, #11,
  #12, #13). Each gets execute + capture + invert. #9 and #13 carry a
  "the message already went out" line in their confirm dialog. #4 and #12 carry the
  complaint-linkability note.
- **S7 - config UI.** `grace_seconds` per stage in the form-SLA config screen, global default in
  Settings.
- **S8 - audit + hardening.** Audit entries on all five paths, SLA event logs for void and reopen
  with `_to_aware_utc()` applied, full test sweep, `/code-review`.

## Tests

- **pytest** - dispatch immediate vs deferred equivalence; idempotent commit under a simulated
  race; partial unique index rejects a second pending; ineligible voiding; guardrail refusal for
  every blocking condition; inverse restores captured prior state; reopen preserves `escalated_at`;
  notify matrix respects per-user channel prefs; every send writes an `integration_log`.
  Every test seeds its own chain (policy -> config -> entity -> tracker) with a marker prefix.
  No `LIMIT 1` off an existing table - CI's database is empty.
- **vitest** - countdown component across all states, remount-safe denominator, eligibility-driven
  button rendering, dialog reason validation.
- **playwright** - approve -> countdown -> undo -> assert nothing changed and no `/api/v1` send
  fired; approve -> let it commit -> post-grace undo -> assert the form returned and the CS task
  is gone. Reached by clicking through the sidebar, never a deep URL.

## Risks

1. **Two code paths drifting.** Mitigated by `execute` calling the unmodified service method and
   by the S0 equivalence test. If anyone inlines logic into `execute`, the feature rots.
2. **Deferral changes a synchronous contract.** Confined to `ui` channel; public token, portal,
   n8n and MCP keep today's shapes (AC-D-3). Verify with a request that carries `X-API-Key`.
3. **Scheduler down = actions stuck.** Lazy commit on read is the safety net; a stuck-pending
   count belongs on the System Health page.
4. **Inverses that are quietly wrong.** This is the real hazard of the 13-action scope. The
   `capture`-then-restore design is what keeps an inverse honest; an inverse that writes a
   constant instead of a captured value should fail review.
5. **A pending action is invisible to other surfaces.** The list page will show the pre-action
   status for up to the grace window. Acceptable at 10s; a `pending` badge on the list row is a
   cheap follow-up if it bites.
6. **No time limit on post-grace undo** means a very old action stays reversible. The guardrail,
   not the clock, is the only thing standing between a stale form and a rewind - so the guardrail
   deserves the heaviest tests in the suite.

## Related, discovered while surveying

The delete-permission gating sweep requested during plan review turned up an authorization gap
that is **not** cosmetic and is tracked separately in `PLAN-permission-gating.md` - 410 routes
with no permission check. It is independent of this feature, ships first, and should not be folded
into these slices.

## Decided

All three plan-review questions are answered and folded into the ACs above:
last-committed-action-only with no time limit; finalize reversal designed and delivered here;
a pending action blocks edit endpoints with `409`.
