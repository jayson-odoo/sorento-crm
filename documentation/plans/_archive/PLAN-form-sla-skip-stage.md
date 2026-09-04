# PLAN - Skip the next SLA stage (complaint: "Settled on site")

**Status:** DONE (Phases 1-3) on `feat/form-sla-skip-stage`, unmerged - grilled 2026-08-03
**UAC:** [UAC-form-sla-skip-stage.md](UAC-form-sla-skip-stage.md) - decisions D1-D14, ACs A1-C10
**Shape:** generic skip capability in the form-SLA engine, one wired consumer (complaint)

## What this is

A stage in a form's SLA chain can declare itself **skippable**. When an authorised
user takes the skip action, the current stage resolves, the next stage never spawns,
and the entity jumps to a terminal status defined by its adapter.

For complaints that means a third outcome beside Approve and Reject: **Settled on
site** - the technician fixed it, no replacement, customer service never involved.

## Why it needs no SLA engine changes

The branch primitive already exists. `_resolve_for_active` (`form_sla_service.py:1116`)
spawns `next_config_id` only when the resolving event matches `advance_on_event`:

```python
advance_on = (getattr(config, "advance_on_event", None) or "").strip()
should_advance = (not advance_on) or (advance_on == (resolve_event or "").strip())
if config.next_config_id and should_advance:
    ...
```

So `complaint.main` with `resolve_event = 'approved,rejected,settled_on_site'` and
`advance_on_event = 'approved'` resolves on a settle without advancing. The
`customer_service` row's own `start_event = 'approved'` doesn't match `settled_on_site`
either, so **both** spawn paths close on one event name. Everything below is plumbing
around that fact.

## Phase 1 - Frontend prototype (mocks, no backend)

Contract the FE codes against, documented at the top of the skip service file:

```
GET  /api/v1/sla/form-sla-tracking?source_entity_type=&source_entity_id=
  -> active tracker gains:
     skip_event: string | null
     skip_action_label: string | null      // "Settled on site"
     can_skip: boolean                     // permission AND stage skippable

POST /api/v1/sla/form/{source_entity_type}/{source_entity_id}/skip
  body: { note?: string }
  200  -> { status: "settled_on_site", resolved_at, message: string }
  403  -> permission denied / handling lock held by another user
  422  -> no adapter | no active tracker | stage not skippable | wrong source status
```

1. `<FormSkipMenuItem>` + `<FormSkipDialog>` in `components/common/` - gear item and
   `AlertDialog` (never `confirm()`), optional note, consequence copy passed in as a
   prop by the adapter-supplied field (D13).
2. Wire into `ComplaintDetail.tsx`'s `<DetailActionsMenu>` beside `Mark as closed`.
3. Stub the hook with fixtures: skippable / not-skippable / no-permission / 403 / 422.
4. `settled_on_site` into `lib/complaint-status.ts` (pill + label),
   `PortalLanding.tsx:76,93` done-bucket, complaint list status filter,
   `FORM_SLA_EVENT_OPTIONS.complaint`.
5. Verify with Playwright MCP via the sidebar (never a deep URL), 1400px and 375px.

Covers **C1, C2, C3, C5, C6, C8, C9, C10**. No backend code this phase.

## Phase 2 - Backend + tests (test-first)

### 2a. Schema

Migration `form_sla_configs` + `skip_event`, `skip_terminal_status`,
`skip_action_label` - all nullable. `skip_event IS NULL` = unskippable = today's
behaviour exactly.

### 2b. Adapter registry

`app/services/form_skip_registry.py` - `source_entity_type` → adapter:

| adapter supplies | complaint |
|---|---|
| model + status column | `Complaint.status` |
| allowed source statuses | `("responded",)` |
| permission slug | `complaint_management.complaints.settle_on_site` |
| consequence copy | "No replacement will be arranged and customer service will not be assigned." |
| contact notify | `_enqueue_respond_message_for_complaint` (one message, `update` = "Settled on site") |
| automation event | `complaint_settled_on_site` |

Adapters carry behaviour; config carries data. Permission lives here, not in config
(D14) - a config row must never mint authority.

### 2c. Endpoint

`POST /api/v1/sla/form/{source_entity_type}/{source_entity_id}/skip`

Order matters: resolve adapter → `assert_can_act_on_form` → permission → active
tracker + `skip_event` present → source status allowed → **write status + `resolved_at`
+ `resolved_by`, commit** → then best-effort, each isolated: Respond.io enqueue,
`emit_form_event(skip_event)`, `dispatch_event(automation_event)`.

Post-commit side effects **must** catch-and-warn (A7). A notify failure that 500s an
action which already committed is the known trap: the caller retries, the retry hits
the wrong-status guard, and the missed side effect is never backfilled.

### 2d. Data migrations

- Append `settled_on_site` to `resolve_event` on `(source_entity_type='complaint',
  stage_code='main')`; set `skip_event='settled_on_site'`,
  `skip_terminal_status='settled_on_site'`, `skip_action_label='Settled on site'`.
  Append-only, idempotent, `advance_on_event` untouched.
- Register permission `complaint_management.complaints.settle_on_site` and grant it to
  every role already holding `.approve`. Idempotent.
- Chain `down_revision` onto a **committed** main head, not a WIP migration, and
  confirm `alembic heads` shows one head after merge.

### 2e. Other backend touches

- `automation_triggers.py` - register `complaint_settled_on_site` `TriggerSpec`
  (inert puller, event-dispatched only, mirroring `complaint_approved`).
- `mcp_tool_capability_service.py:1569,1591` - add to the status enumeration.
- `permission_registry.py` - the new slug + description.
- **Not touched, deliberately:** `LINKABLE_STATUSES`, `_VOID_BLOCKED_STATUSES`. Their
  absence is the design (D4, D9).

### 2f. Tests

- **pytest** - A1-A8, B1-B9. **B3 is the load-bearing one**: after a skip the `main`
  tracker is resolved AND no `customer_service` tracker exists. **B6** is the
  regression guard: a DO naming a settled complaint must not link it or revert it.
  Postgres only, `tests/_pg_fixture.py`, seed real FK targets, scope all cleanup to
  marker rows.
- **vitest** - C1-C6 on the shared components and the complaint wiring.
- **playwright** - sidebar → complaint → gear → Settled on site → assert pill, assert
  gear item gone, assert `browser_network_requests` shows the skip POST and **both**
  tracker queries refetching (C4).

## Phase 3 - Review

`/code-review` on the branch, then `documentation/PR-CHECKLIST.md`. PR description
carries the Phase 1 screenshot, the three green suites, and a note that the shipped
contract matches Phase 1.

## Risks

| risk | mitigation |
|---|---|
| Config row missed → `main` tracker never resolves; a closed complaint escalates and WhatsApps assignees for days | Migration, not an admin step (D11). B9 asserts it. |
| New permission granted to nobody → gear item invisible, reads as broken | Copy-from-`.approve` grant migration (D6). B8 asserts it. |
| `complaint_approved` automations silently stop covering settled complaints | Accepted and documented (D10). List the configured automations in the PR so each can be duplicated or not, per automation. |
| Gear placement hides the action from the people who asked for it | Accepted. If adoption is low, promote to a header button - the stakeholder originally asked for it *beside* Approve/Reject. |
| Status-label maps missed → portal shows a settled complaint as still open | C6 enumerates all four sites. |

## Adjacent defects found while grilling - fix separately

1. **`sponsorship_form.project_sales_manager.advance_on_event IS NULL`** → rejecting a
   sponsorship form spawns the customer-service stage and assigns someone to a rejected
   form. `purchase_request.main` is NULL too. Same code path; separate PR so it can be
   reviewed and reverted independently.
2. **131 enabled duplicate `complaint_approved` automations** on the dev DB
   (`e2e@test.local` / `x@x.com`, 2026-07-24) - one approval sends 131 emails locally.
   Prod not yet checked.
