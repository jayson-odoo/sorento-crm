# UAC - Skip the next SLA stage (complaint: "Settled on site")

**Status:** DONE (Phase 1 + Phase 2 + Phase 3 self-review) on `feat/form-sla-skip-stage`, unmerged.
Backend 27 pytest green, frontend 25 vitest green (full suite 1363), real browser round-trip verified.
**Grilled:** 2026-08-03 (16 decisions, this doc is the record)
**Plan:** [PLAN-form-sla-skip-stage.md](PLAN-form-sla-skip-stage.md)

## Journey

**Actor:** the technical team reviewer, on the complaint detail page.

**Where they arrive from:** a technician attended the customer's site and wrote up
what they found. That write-up is `technical_team_response`, and sending it is what
moved the complaint `submitted → responded`. So by the time the reviewer opens this
page, the visit has already happened and the outcome is already known - nothing is
being scheduled, only recorded.

**What the system already knows:** the complaint, the customer, the delivery order,
the technician's response, the root cause, and who is on the complaint team. It does
not know one thing: **was a replacement needed, or did the technician fix it there?**
That is the single decision this journey exists to capture.

**The steps:**

1. Reviewer opens the complaint at `responded`. Header shows `Approve` and `Reject`.
2. They pick the outcome that matches what actually happened:
 - **`Approve`** - a replacement is needed. Customer service takes it from here.
 - **`Reject`** - the issue is not product-related. Reason required.
 - **`Settled on site`** (gear menu) - the technician fixed it. Nothing more to do.
3. For `Settled on site`: a confirm dialog states the consequence in the adapter's own
   words ("No replacement will be arranged and customer service will not be assigned"),
   offers an optional note, and asks them to confirm.
4. One click. The complaint is done.

**What they hold at the end:** a complaint at `settled_on_site`, terminal, with no
customer-service assignment and no running SLA clock.

**What everyone else is told automatically:** the contact gets one Respond.io message
("status changed to settled on site by our technician", plus the note if given). The
`main` SLA tracker resolves, so nobody is chased about it. Any admin-configured email
automation on `complaint_settled_on_site` fires. Customer service is never notified,
because customer service was never involved.

**Why "Approve" stopped being enough:** `Approve` names a *validity judgement* while
the thing that actually routes the complaint is the *remedy*. Those came apart the
moment a technician could settle something on site - a valid complaint with no
replacement had nowhere to go. Approve now means exactly one thing: pass it to CS.

## Decisions

- **D1 - Mechanism is the existing `advance_on_event` branch, not new engine code.**
  A stage resolves on any event in `resolve_event`, but only spawns `next_config_id`
  when the resolving event equals `advance_on_event`. Adding `settled_on_site` to
  `complaint.main.resolve_event` while leaving `advance_on_event = 'approved'` closes
  the chain. The CS stage's own `start_event = 'approved'` doesn't match either, so
  both spawn paths close on one event name. **Zero SLA engine changes.**
- **D2 - One CTA per outcome; the third lives in the gear.** `Approve` and `Reject`
  stay header buttons; `Settled on site` is a gear item. Precedent: `Mark as closed`,
  the other alternate terminal, is already a gear item while the expected terminal
  `Processed by CS` is a header button. Rejected: a checkbox inside the Approve dialog
  (buries a peer outcome under a verb that already misleads); a radio group (same).
- **D3 - Terminal in one transaction.** `responded → settled_on_site` directly. No
  pass through `approved`, no second click. The technician's visit already happened
  (see Journey), so there is nothing to wait for. Rejected: parking at `approved` with
  no CS tracker - no assignee, no clock, no escalation, invisible to the overdue scan.
- **D4 - New status code `settled_on_site`, not `fulfilled` + a marker column.**
  More files, less logic. `settled_on_site` is absent from `LINKABLE_STATUSES`, so it
  is *inherently* immune to the DO auto-linker; reusing `fulfilled` would have needed
  two pieces of defensive code (an auto-link gate and a revert gate) to stop the
  reconciler pushing a settled complaint into `processed_by_cs` - the CS stage we
  deliberately skipped, with no tracker behind it.
- **D5 - Canonical term `settled_on_site` in all five places:** status code,
  permission slug, SLA `resolve_event` value, event-log name, UI label ("Settled on
  site"). One spelling, no translation layer.
- **D6 - New permission `complaint_management.complaints.settle_on_site`**, not a
  reuse of `.approve`. Follows the registry's own documented precedent (`.close` is
  separate from `.resolve` "so it can be granted/hidden independently"). Ships with a
  data migration granting it to every role that already holds `.approve` - a new
  permission is granted to nobody on creation, and an invisible gear item is
  indistinguishable from a broken feature.
- **D7 - Optional note, nothing else.** Mirrors `Processed by CS` / `Mark as closed`.
  Rejected: requiring `resolution` (Repair/Rework/Replacement with Parts) - that field
  is `Optional` in all three schemas, NULL on most rows, and contradicted where set
  (a `Repair` complaint reached CS; a `Replacement with Parts` one was rejected).
  Making it mandatory on the rarest path produces junk, not data. Fixing resolution
  data quality is its own change, required at *response* time on every path.
- **D8 - Routing cannot be inferred, it must be asked.** Checked: `resolution_id`
  would be the natural signal and it is not trustworthy (see D7).
- **D9 - Stays voidable.** `settled_on_site` is NOT added to `_VOID_BLOCKED_STATUSES`,
  matching `fulfilled` today. Void (irreversible, reason-required, notifies) is the
  recovery when a settle turns out to be wrong. Rejected: a re-open/undo endpoint -
  real scope, and it would have to decide whether to resurrect or respawn the `main`
  tracker and what the contact is told about a status going backwards.
- **D10 - New automation event `complaint_settled_on_site`.** The event drives only
  admin-configured emails (`dispatch_event` → `automations WHERE trigger_type = ...`
  → `send_email`); it touches neither SLA nor Respond.io nor n8n. Reusing
  `complaint_approved` would emit `"status": "approved"` for a complaint that isn't,
  poisoning a field automations branch on. **Consequence to accept:** automations
  wired to `complaint_approved` do not fire for settled complaints until an admin adds
  one on the new event.
- **D11 - Config change ships as an idempotent data migration**, not an admin task.
  Appends `settled_on_site` to `resolve_event` on `(source_entity_type='complaint',
  stage_code='main')` - append-only so it cannot clobber an admin edit, no-op if
  already present. If this row is missed, settle emits an event no config matches, the
  `main` tracker never resolves, and a closed complaint keeps escalating and
  WhatsApping assignees. Too quiet a failure to leave to a human step.
- **D12 - Generic plumbing, complaint the only wired consumer.** The *capability* is
  general (config columns + adapter registry + one endpoint + one shared FE component);
  the *semantics* stay per-domain. Rejected: shipping skip for `purchase_request` /
  `sponsorship_form` / `stock_inquiry` now - that means inventing what "skip" means for
  three domains nobody has asked about.
- **D13 - Config supplies the label; the adapter supplies the consequence copy.** A
  config-authored string must never be the only thing telling a user "no replacement
  will be arranged" - that sentence is domain truth.
- **D14 - Permission stays per-entity, resolved by the adapter.** A config row must
  never mint authority; otherwise inserting a row silently grants the action to anyone
  who can see the page.

## Acceptance criteria

### Group A - Generic skip engine (backend)

**A1 - Config declares a skip.** `form_sla_configs` gains `skip_event`,
`skip_terminal_status`, `skip_action_label` (all nullable). A stage with
`skip_event IS NULL` is unskippable and behaves exactly as today. *BE + pytest.*

**A2 - Adapter registry.** A registry maps `source_entity_type` → adapter supplying:
model + status column, permission slug, consequence copy, contact-notify callable,
automation event name. Registering an adapter is the only code needed for entity #2.
*BE + pytest.*

**A3 - Generic endpoint.** `POST /api/v1/sla/form/{source_entity_type}/{id}/skip`
with optional `note`. Order: resolve adapter → `assert_can_act_on_form` → permission
check → active-tracker + skippable-stage check → write terminal status → commit →
best-effort side effects. *BE + pytest.*

**A4 - Unknown / unskippable → 4xx.** No adapter for the type, no active tracker, or
active stage has no `skip_event` → 400 with a specific message, no state change. *BE.*
The ROUTE returns 422 earlier for an entity type that is not a form-SLA type or has
no registered adapter; the SERVICE guards return 400 via `handle_validation_error`,
which is the code `decide_complaint` already returns for its own wrong-status guard.
One page, one convention.

**A5 - Permission denial → 403**, before any write. *BE.*

**A6 - Handling lock respected.** An escalated form locked to another user → the
same 403 `assert_can_act_on_form` produces for `/approve` today. *BE.*

**A7 - Post-commit side effects are best-effort.** Respond.io enqueue, SLA emit and
automation dispatch each catch-and-warn. A failed notify never 500s an action that
already committed, and never rolls back the status. *BE + pytest.*

**A8 - Tracker payload exposes skip fields.** `form-sla-tracking` returns
`skip_event`, `skip_action_label`, and a resolved `can_skip` boolean for the caller.
*BE + pytest.*

### Group B - Complaint adapter

**B1 - Happy path.** Complaint at `responded`, user holds `.settle_on_site` → skip →
200; status `settled_on_site`; `resolved_at` / `resolved_by` stamped. *BE + pytest.*

**B2 - Wrong source status → 400.** Any status other than `responded` is refused,
matching `_DECIDE_ALLOWED_FROM_STATUSES`. *BE + pytest.*

**B3 - `main` tracker resolves, CS never spawns.** After skip: the `main` tracker is
`is_resolved = true`; **no** `customer_service` tracker exists for the complaint.
*BE + pytest - this is the core assertion of the whole feature.*

**B4 - One contact message.** Exactly one Respond.io message enqueued: *"There has
been an update regarding your complaint{ for DO-x}: status changed to settled on site
by our technician.{ Note: …}"*, `update` template var `"Settled on site"` (+ note).
Zero messages when the complaint has no `respond_inbox_url`, status still commits.
*BE + pytest.*

**B5 - Automation fires.** `complaint_settled_on_site` dispatched with the same
context shape as `complaint_approved` but `"status": "settled_on_site"`. Fires nothing
when no automation is configured. *BE + pytest.*

**B6 - DO auto-linker ignores it.** A DO naming a `settled_on_site` complaint in
Remarks CS does **not** link it and returns the existing not-linkable warning. The
complaint is never reverted to `processed_by_cs`. *BE + pytest - regression guard.*

**B7 - Still voidable.** `Void` remains available on a settled complaint (D9). *BE.*

**B8 - Permission granted on migration.** Every role holding `.approve` before the
migration holds `.settle_on_site` after it. Idempotent on re-run. *BE + pytest.*

**B9 - Config migration.** `complaint.main.resolve_event` contains `settled_on_site`
after migrate; `advance_on_event` still `approved`; re-running changes nothing; an
admin-added event in the CSV survives. *BE + pytest.*

### Group C - Frontend

**C1 - Gear item, config-driven.** `<FormSkipMenuItem>` renders in the detail gear
menu only when the active tracker declares a skip AND the user holds the permission.
Label from `skip_action_label`. *FE + vitest.*

**C2 - Hidden otherwise.** No active tracker, non-skippable stage, missing permission,
voided form, or a handling lock held by someone else → not rendered. *FE + vitest.*

**C3 - Confirm dialog.** `AlertDialog` (never `confirm()`), consequence copy from the
adapter, optional note field, confirm + cancel. *FE + vitest.*

**C4 - Success.** Confirm → `POST .../skip` → toast, detail refetches, status pill
reads "Settled on site", gear item gone, `Approve` / `Reject` gone. **Both** the
`form-sla-tracking` and `form-sla-trackers` queries invalidate (the lock banner and
the SLA banner are two separate queries - invalidating one leaves the other stale).
*FE + vitest + playwright.*

**C5 - Error.** Failure → `extractApiError` message in a toast, dialog stays open,
status unchanged. *FE + vitest.*

**C6 - Status labels everywhere.** `settled_on_site` added to
`lib/complaint-status.ts` (pill colour + label), `PortalLanding.tsx:76,93` (the
contact-facing done bucket - omit it and the portal shows a settled complaint as still
open), and the complaint list's status filter. *FE + vitest.*

**C7 - MCP tool description.** `mcp_tool_capability_service.py:1569,1591` status
enumeration includes `settled_on_site`, or the AI assistant cannot answer "show me
settled complaints". *BE.*

**C8 - Admin config catalog.** `FORM_SLA_EVENT_OPTIONS.complaint` includes
`settled_on_site` so admins can wire it into future stages themselves. *FE.*

**C9 - Mobile.** Gear item and dialog usable at 375px; dialog scrolls
(`max-h` + `overflow`). *FE + playwright.*

**C10 - Reached via the sidebar.** Playwright navigates Complaint Management →
Complaints → row → gear, never a deep URL. *FE + playwright.*

## Out of scope (raised during the grill, deliberately not built)

- **Skip for `purchase_request` / `sponsorship_form` / `stock_inquiry`.** Per D12 -
  the engine supports them; the semantics are undefined. Each needs an adapter, a
  status code, a permission and contact wording, decided with the people who use them.
- **`Reject` relabel** to something narrower than the generic verb (the stakeholder
  described it as "attended by technician, issue not product-related"). Pending.
- **Re-open / undo** (D9 - void is the recovery).
- **`resolution_id` data quality** (D7 - needs to be required at response time).

## Adjacent defects found while grilling (NOT fixed here)

1. **`sponsorship_form.project_sales_manager` has `advance_on_event = NULL`**, so
   *any* resolve advances - **rejecting a sponsorship form spawns the customer-service
   stage** and assigns someone to a rejected form. `purchase_request.main` is NULL too
   and needs the same look. Same family as the known `advance_on_event` gap. Sits in
   the exact code path this feature touches; fix separately so it can be reviewed and
   reverted on its own.
2. **131 enabled duplicate `complaint_approved` automations** on the dev DB, all
   created 2026-07-24 with recipients `e2e@test.local` / `x@x.com` - E2E leftovers on
   a prod-data copy. Approving one complaint locally sends 131 emails. Prod not yet
   checked.

## Verification log (Phase 3 self-review)

Ran against `documentation/reference/PR-CHECKLIST.md`. Most CRUD items are N/A: this
ships an action on an existing detail page, not a new entity. Applicable items pass -
`extractApiError` is used (no hand-rolled `response.json().catch`), the confirm is an
`AlertDialog` carrying "This action cannot be undone" (never the browser `confirm()`),
and no `buildDataGridParams` / user-select helper is duplicated.

Two defects found by the review itself, both fixed here:

1. **Wrong stage could be skipped when several are active.** `_active_skippable_stage`
   ordered by `created_at DESC` while `GET /form-sla-tracking` orders by
   `initiated_at DESC`. Form SLA is multi-active by design, so with two unresolved
   stage rows the service could close a different stage from the one whose label the
   user clicked - silently, since both calls return 200. Now both use `initiated_at`,
   pinned by `test_a3_service_picks_the_same_stage_the_frontend_offered`.
2. **Em-dashes throughout** (banned by CLAUDE.md for all writing including comments).
   153 occurrences replaced with spaced hyphens across authored files and added lines.

Known limitations, deliberately not addressed:

- **`skip_event` is not editable in the admin Form SLA Config UI.** `settled_on_site`
  is in `FORM_SLA_EVENT_OPTIONS` so an admin can wire it into `resolve_event`, but the
  three skip columns are set by migration only. Entity #2 therefore needs a migration
  or SQL for its config row, not just an adapter. Worth a follow-up if a second
  consumer lands.
- **A tracker with NULL `team_set_code` is never skippable.** The config lookup binds
  the value as a parameter, so `= NULL` matches nothing. Fails closed, which is the
  right direction, but it is an implicit behaviour rather than a stated rule.
- **The complaint page also gates the gear item on `status === 'responded'`**, which
  duplicates the adapter's `allowed_source_statuses` in the frontend. Redundant (the
  CS stage declares no skip, so the item would hide anyway) and mirrors how Approve /
  Reject are gated, but it is domain knowledge living in two places.
