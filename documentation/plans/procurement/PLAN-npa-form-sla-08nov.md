# Plan: NPA approval and purchasing through Form SLA config (NPA-FORM-SLA)

Status: Review (built; owner answered Q1-Q5 8 Nov 21:45 and the team-notice follow-up), 8 Nov 2026. Size M, full track (data-only migration, RBAC gate
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

## Who gets what notice (owner 8 Nov: "like SI", Q2 b + team notice b)

| Move                         | Before                                | After                                                    |
|------------------------------|---------------------------------------|----------------------------------------------------------|
| Submit / Resubmit            | every `.approve` holder               | approval stage's assignee (SLA assignment notice) + the SI's team notice to the `lead_time_enquiries` / `project_sales` team |
| Approve                      | every `.open_code` holder             | purchasing stage's assignee + the SI's team notice to the `purchasing` team |
| Revise (from Submitted or Approved) | every `.approve` holder (from Submitted only) | whoever held the voided stage (assignee, lock holder); nobody when no stage was open |
| Reject, purchasing Reject    | applicant                             | applicant (unchanged)                                    |
| Complete                     | applicant                             | applicant (unchanged)                                    |
| Overdue                      | nothing                               | escalation to the next tier team, as the SI              |

Correction to the first card (Q2): the SI is not silent without a stage row. Apart from the
engine it sends a fixed team notice (`procurement_service.py:5452` `_notify_team_stock_inquiry`,
called at `api/v1/procurement/stock_inquiries.py:435-445` and `procurement_service.py:7249`).
The NPA now sends that same notice through the same function, which takes the form type, company,
link and button label (a stock inquiry passes none of them and is unchanged). With no NPA stage
row, the team notice still goes and no stage notice goes, exactly as on the SI. The
permission-holder broadcast is gone.

## Gating

Permission check stays as it is (`.approve`, `.open_code`, Q3 a); every approver / purchasing move
(approve, reject, purchasing response save / reply, feedback, new code link / close / undo, line
link / close / undo, purchasing reject) also calls `assert_can_act_on_form(..., source_entity_type=
"new_product_application")`, exactly as the SI routes. The SLA tracker readers admit the NPA's own
view-all slugs (`.view`, `.approve`, `.open_code`) for NPA trackers (`api/v1/sla/sla_tracking.py:67`).
The applicant's own moves (submit, revise, cancel) are not stage work and are not gated. The lock
itself stays off until an admin ticks New Product Application in System Settings > handling lock
(Q4 a; the switch list gained the type).

## NPAs already open

No backfill (owner Q1 a): an NPA submitted or approved before this ships has no tracker; it finishes
under today's rules (no tracker = `assert_can_act_on_form` allows). Its moves still send the SI's
team notice; no stage notice goes, as for any move with no stage row. The first NPA move after ship
that starts a stage (a resubmit, an approve of an already-submitted one) starts it normally.

## Accepted gaps (review, 8 Nov; follow-ups, not this lane)

- Undo after Completed (undo the new code or a line, or clear the outcome) moves the NPA back to
  Approved, but its purchasing stage stays resolved: nothing restarts it, so it no longer escalates.
  The SI has no undo, so there is no SI behaviour to copy; trigger for a follow-up: an owner report
  of an undone NPA left without a task.
- Revise / Cancel void the open stage but do not void a pending take-over request on it (the SI's
  revision does, after its commit; the price tag re-escalation has the same gap).
- The shared SLA Tracking tab shows a voided stage as Pending with time remaining: the tracker
  response carries no `voided_at`. Same on the SI today (shared component). The backend is right
  (voided, not resolved, out of the KPIs); the tab needs `voided_at` in the response and a Voided
  status, for every form type.

## Who may open and act (crew pass 8 Nov)

The stage assignees must be able to open the NPA. On dev the Project Sales Manager role (approval
assignee) and the purchasing tier-1 role held no NPA permission, while on the SI they hold the stage
slugs. The data migration copies the grants from the SI's own holders (as `npa_0001` did for
`create`): `procurement.stock_inquiries.project_sales_approve` -> NPA `view` + `approve`,
`procurement.stock_inquiries.purchasing_reject` -> NPA `view` + `open_code`. Additive, idempotent,
no role named; the downgrade leaves grants alone. Owner answer to the crew-ask pending (option a
recommended); built so it can ship on a yes.

An applicant with only `create` + `view_own` is limited: like the SI, they see the portal form, no
tab strip and so no SLA tab.

## Seed

Data-only alembic migration `npasla_0001_seed_configs` (owner Q5 a): copies the two SI rows (by team set `project_sales` /
`purchasing`) into NPA rows with the NPA event names, `WHERE NOT EXISTS` an NPA row for that team
set. Idempotent, a no-op where the SI rows do not exist (CI). Downgrade deletes only the rows it
can recognise as its own (type NPA + those stage codes). Also posted as `crew-migration:` SQL for
the shared dev DB.

Dev (crew data 8 Nov): SI rows `project_sales` (policy Stock Inquiries) and `purchasing` (policy
Normal Sorento Policy) exist on `lead_time_enquiries`; no NPA row or tracker yet; no NPA is
submitted today (2 approved: NPA-000008, NPA-000005), so the hand test submits a fresh one. The
SI's purchasing row also resolves on `purchasing_respond` (its response ends it); the NPA's
resolves on completed / rejected, because a Save only response comes before the code is opened.

## FE

- `FormSLAConfigDialog` type list + `FORM_SLA_EVENT_OPTIONS` / `FORM_SLA_TYPE_LABELS` gain
  `new_product_application`.
- My Pending, the SLA KPI dashboard task list, the Form SLA Tracking list and the SLA WhatsApp
  `form_url` (`form_sla_service.py` `_FE_RECORD_ROUTES`) route an NPA task to the NPA.
- The SI team-notice email's seeded row (`eml_0002_seed_layouts`) reads its button label from
  the notice, only while the row is still exactly as seeded (same data migration).
- The shared SLA tab names the record by its type label ("new product application").
- NPA detail: an SLA Tracking tab rendering the SI's `FormSLATrackingTab` (view-all holders only,
  the same slugs the BE admits), the SI's `HandlingLockBanner` + release menu item, and the
  approver / purchasing buttons disabled while another person holds an escalated stage. The page
  keeps its own strip (Details / Stock inquiry) rather than the `FormDetailWithSLATabs` shell,
  whose Details-tab structure it does not have.
- System Settings handling-lock switch lists New Product Application.

## Tests (red first)

BE (`tests/test_npa_form_sla.py`): type lists agree; seed copies SI rows and is idempotent;
submit starts approval tracker and notifies only its assignee; approve resolves it and starts
purchasing; purchasing response stops the response clock; complete / purchasing reject resolve;
revise / cancel void; no stage row tells no permission holder; team notice per move with and
without a stage row; escalated + lock on: non-holder approve 403, holder 200; tracker reader admits
`.approve` holder for NPA trackers only. FE: dialog offers the type; NPA detail renders the SLA tab.
