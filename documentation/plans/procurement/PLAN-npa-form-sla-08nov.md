# Plan: NPA approval and purchasing through Form SLA config (NPA-FORM-SLA)

Status: Build (behaviour card posted as crew-ask on PR #2261; building on the recommended answers
until the owner says otherwise), 8 Nov 2026. Size M, full track (data-only migration, RBAC gate
change on approve / reject / purchasing moves). Owner ask 8 Nov ("2233 sla a + same teams"): the
New Product Application's approver / processor flow works like the Stock Inquiry's, through Form SLA
config, same component and same engine.
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

## Today (measured, main 3a6c57ed)

- Approve / reject: anyone holding `procurement.new_product_applications.approve`
  (`services/new_product_application_service.py:456-480`). Purchasing (response, link / close the
  new code, purchasing reject): anyone holding `.open_code` (`:483`, `:647`, `:725`).
- Notices: `notify()` (`:1748`) emails + in-app EVERY holder of `.approve` on submit / resubmit /
  withdraw, EVERY holder of `.open_code` on approve, and the applicant on reject / complete. Both
  routers call it after their commit (`api/v1/procurement/new_product_applications.py:77`,
  `api/v1/public/portal_new_product_application.py:71`).
- No SLA: `new_product_application` is not a form SLA type (`form_sla_service.py:34`,
  `schemas/sla.py:656`, `FormSLAConfigDialog.tsx:124`), so no tracker, no due date, no escalation,
  no handling lock, no SLA tab on the NPA page (tabs: Details / Stock inquiry,
  `NewProductApplicationDetail.tsx:518`).
- The SI (crew dev evidence, 8 Nov): two `form_sla_configs` rows on agent `lead_time_enquiries`:
  team set `project_sales` (start submit, resolve approve / reject / voided; tier 2 Project Sales
  Manager, tier 3 Project Director, tier 1 unset so it starts at 2) and team set `purchasing`
  (start project_sales_approve, respond purchasing_respond; tiers Purchasing - Product, Stock
  Inquiry / Purchasing Manager / Retail Director). Rows are admin data,
  not seeded by any migration (grep `alembic/versions` for `lead_time_enquiries`: none). Engine:
  `FormSLAOrchestrator` (`form_sla_service.py:359`): start = tier team round robin with tier
  fallback (`:918`), overdue scan escalates (`:574`). SI routes gate every move with
  `assert_can_act_on_form` (`api/v1/procurement/stock_inquiries.py:514-731`) ON TOP OF the
  permission: the lock only bites once a stage has escalated and the type is in
  `system_settings.handling_lock_enabled_types` (`handling_lock_service.py:156`).

## Stage map (what ships)

Two NPA rows, `source_entity_type = new_product_application`, same agent, same team sets, same
policy, same notify flags as the SI rows (stage identity is (type, team set), so sharing the SI's
team sets cannot collide with SI trackers, `form_sla_service.py:860`):

| Stage (team set)         | Starts on                    | Response clock stops on | Resolves on            |
|--------------------------|------------------------------|-------------------------|------------------------|
| approval (`project_sales`) | `submitted`, `resubmitted` | (none, as the SI)       | `approved`, `rejected` |
| purchasing (`purchasing`)  | `approved`                 | `purchasing_respond`    | `completed`, `rejected`|

Event names are the NPA's own move names (the ones `notify()` already receives), plus
`purchasing_respond` (any save of the purchasing response dialog). Revise and Cancel VOID the open
stage (`void_active_for_source`, as the SI revision and the price tag re-escalation do), they do
not resolve it, so a withdrawn NPA never counts as handled in the KPIs.

## Who gets what notice

| Move                         | Today                                 | After                                                    |
|------------------------------|---------------------------------------|----------------------------------------------------------|
| Submit / Resubmit            | every `.approve` holder               | the approval stage's assignee only (SI's SLA assignment notice, with due date) |
| Approve                      | every `.open_code` holder             | the purchasing stage's assignee only                     |
| Revise / withdraw            | every `.approve` holder               | the voided stage's assignee only                         |
| Reject, purchasing Reject    | applicant                             | applicant (unchanged)                                    |
| Complete                     | applicant                             | applicant (unchanged)                                    |
| Overdue                      | nothing                               | escalation to the next tier team, as the SI              |

Fallback (Q2): when no active NPA stage row exists (config deleted / switched off, a fresh tenant,
CI), the move falls back to today's broadcast, so nobody goes unheard.

## Gating

Permission check stays as it is (`.approve`, `.open_code`); every staff move that changes state
(approve, reject, revise, purchasing response save / reply, new code link / close / undo, line
link / close / undo, purchasing reject) also calls `assert_can_act_on_form(..., source_entity_type=
"new_product_application")`, exactly as the SI routes. The SLA tracker readers admit the NPA's own
view-all slugs (`.view`, `.approve`, `.open_code`) for NPA trackers (`api/v1/sla/sla_tracking.py:67`).

## NPAs already open

No backfill (Q1): an NPA submitted or approved before this ships has no tracker; it finishes under
today's rules (no tracker = `assert_can_act_on_form` allows; notices fall back to the broadcast for
that move only if no stage starts). The first NPA move after ship that starts a stage (a resubmit,
an approve of an already-submitted one) starts it normally.

## Seed

Data-only alembic migration `npasla_0001`: copies the two SI rows (by team set `project_sales` /
`purchasing`) into NPA rows with the NPA event names, `WHERE NOT EXISTS` an NPA row for that team
set. Idempotent, a no-op where the SI rows do not exist (CI). Downgrade deletes only the rows it
can recognise as its own (type NPA + those stage codes). Also posted as `crew-migration:` SQL for
the shared dev DB.

## FE

- `FormSLAConfigDialog` type list + `FORM_SLA_EVENT_OPTIONS` / `FORM_SLA_TYPE_LABELS` gain
  `new_product_application`.
- NPA detail: the SI's `FormDetailWithSLATabs` shell (Details / Stock inquiry / SLA Tracking) and the
  SI's handling lock banner, same components, same path.

## Tests (red first)

BE: type lists agree; seed copies SI rows and is idempotent; submit starts approval tracker and
notifies only its assignee; approve resolves it and starts purchasing; purchasing response stops
the response clock; complete / purchasing reject resolve; revise / cancel void; no config falls
back to broadcast; escalated + lock on: non-holder approve 403, holder 200; tracker reader admits
`.approve` holder for NPA trackers only. FE: dialog offers the type; NPA detail renders the SLA tab.
