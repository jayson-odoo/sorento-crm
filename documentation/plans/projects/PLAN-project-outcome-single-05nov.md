# PLAN: One Won/Lost outcome per project (drop per-area outcome)

Status: Review (built; owner answered 5 Nov ~12:40). Track: standard, size M, no migration.

Lane: PROJECT-OUTCOME-SINGLE. Owner ruling 5 Nov 2026 12:28 MYT: "we don't need per area
outcome" / "we only need per project outcome, simple as that".

## Facts (re-verified on main 30bbcc6a)

Per-area outcome `ProjectQuotation.outcome` + `loss_reason` + `decided_at`
(`app/models/projects.py:1795-1802`). Writers and readers:

| # | Where | What it does today |
|---|-------|--------------------|
| W1 | `project_quotation_service.py:1423` `set_outcome`, route `POST /quotations/{id}/outcome` (`api/v1/projects/quotations.py:213`) | Win/lose/reopen one area, then `sync_project_outcome` |
| W2 | `project_quotation_service.py:1460` `derive_project_outcome` / `:1481` `sync_project_outcome` | Project won if ANY area won, lost only if ALL lost. Also called on area delete `:486` |
| W3 | `project_quotation_document_service.py:1684,1688-1711` `_win_the_scopes_on` | Customer accept wins every non-lost area of the signed issue |
| R1 | `project_forecast_service.py:139` `_open_quotation_totals` | Pipeline sums OPEN areas only |
| R2 | `project_forecast_service.py:394-410` `loss_reason_counts` | Loss-reasons report counts per-area loss reasons (missed by the first audit) |
| R3 | `project_quotation_document_service.py:912,963,975` make quotation | Needs derived outcome won; skips lost areas; copies created won |
| R4 | `project_po_reading.py:129-134`, `project_po_confirm.py:333-337` | PO binds to the best area: won > open > lost; ties left unbound |
| FE1 | `quotation-documents/[documentId]/components/QuotationScopesTab.tsx:97-128` | Outcome pill + Record outcome (removed by #2194) |
| FE2 | `[projectId]/quotations/[quotationId]/components/QuotationDetailClient.tsx:82,118` | Unlinked per-area page: pill + Record/Change outcome |
| FE3 | `quotation-documents/components/QuotationFormClient.tsx:915,947` | Outcome pill on the saved-area strip |
| FE4 | `[projectId]/components/QuotationOutcomeDialog.tsx` | The per-area outcome dialog |

Project-level `Project.outcome` (`projects.py:349`) + `loss_reason` (`:350`): stored, but only
W2 writes it. Readers: forecast live/lost sets `project_forecast_service.py:241,268,371`,
staleness `project_staleness_service.py:116,235`, clash `project_clash_service.py:303`, task phase
`project_task_service.py:509`, pipeline filter `project_service.py:1149`, FE "Make quotation"
gate `quotation-documents/actions.tsx:75,157`.

Status rungs (`project_seed_service.py:53-63`): Lost, Dormant, PO Received are TERMINAL, and the
status engine refuses any outgoing edge from a terminal rung (`status_service.py:374-383`), so
nothing can move a project out of Lost today. `change_status` (`project_service.py:1468`) never
writes outcome, so a project on "Lost" still reads outcome `open` and stays in the pipeline
(drift; the FE comment at `ProjectDetailClient.tsx:281` assumes the opposite). The first PO
auto-moves to PO Received (`project_po_service.py:406,460`), also without touching outcome.

## Behaviour card (proposed)

Rules:
1. A project has ONE outcome: Open, Won or Lost (`Project.outcome`). Areas have no outcome.
2. Lost: the existing "Mark lost" status move. It now asks for a loss reason (same configurable
   list as today) and sets outcome Lost + `Project.loss_reason`.
3. Won: any of (a) "PO received" status move, manual or the automatic one on the first PO;
   (b) the customer accepts a proposal online; (c) a new "Mark won" gear item on the project page,
   for a yes before any PO (needed so "Make quotation" can run). (c) does not move the status.
4. Re-open: a "Re-open" gear item on a Won or Lost project sets outcome Open and clears the loss
   reason. If the project sits on the Lost rung it goes back to the rung it was on before Lost
   (from its own stage-changed history; the initial rung if none).
5. Forecast: an Open project's pipeline is the latest version of every area on its proposals;
   Won or Lost contributes no pipeline (Committed still counts POs, lost projects included).
   The loss-reasons report counts projects by `Project.loss_reason`.
6. Make quotation: allowed on an Open or Won project, refused on a Lost one; copies every area
   of the chosen revision.
7. PO intake: no outcome ranking. Project has a quotation: the PO checks against it (unchanged).
   Otherwise: one area binds to it, two or more is the person's call (left unbound, as a tie is
   today).
8. Per-area page `[projectId]/quotations/[quotationId]` (FE2): nothing links to it; deleted.
   `POST /quotations/{id}/outcome` and `QuotationOutcomeDialog` are removed.

Edge cases:
- Customer signs a proposal on a Lost project: acceptance recorded, outcome stays Lost (a person
  decided it, same reasoning as today's "lost area is left alone").
- Customer signs on a Won project: no change.
- Deleting an area no longer recomputes anything.
- Dormant rung: outcome stays as it is (out of scope; ruling says Open/Won/Lost).

## Owner answers (5 Nov ~12:40, verbatim)
"One loss is set at the project level. Yeah, we can reuse the stage move. Forecast A. Make
quotation. No, allow it on an open project. It doesn't need to be a warm project. The PO is checked
against the quotation. No? Don't need to fix existing data. This is not rolled out yet."

- Q1 (a) reuse the stage moves + gear Mark won / Re-open.
- Q2 (a) forecast as proposed.
- Q3 (b) Make quotation on an Open project too; still refused on Lost (stated in the PR).
- Q4 (a) PO checks against the quotation; the won/open/lost area ranking goes.
- Q5 (b) no data fix, no migration (project sales not rolled out). Per-area columns stay, unused.
- Unlinked per-area page: deleted.

## Steps (after answers)
1. Tester: red pytest for rules 2-8 + vitest for the gear items / dialog / removed pills.
2. Coder: BE (status hook, mark won/re-open endpoints, forecast, make quotation, PO ranking,
   accept path, remove W1/W2), FE (gear items, dialog, pill removal, delete FE2).
3. Reviewer + kill test; cloud browser pass; hand-test script; guide update.

## Build contract (tester and coder work from this, verbatim)

### Backend

- **BE1 Mark lost = stage move.** `POST /api/v1/projects/projects/{id}/status` (route
  `api/v1/projects/projects.py:637`). `ProjectStatusChangeRequest` (`schemas/projects.py:336`) gains
  `loss_reason: Optional[str] = None`. In `project_service.change_status` (`:1468`), after the
  transition check, branch on the TARGET status key:
  - `lost`: `loss_reason` is validated with `project_quotation_service._assert_loss_reason` (same
    lookup set and the same 422 codes: `quotation_loss_reason_required`,
    `quotation_loss_reason_invalid`, `quotation_loss_reasons_unconfigured`), checked BEFORE
    `status_id` is written (a refusal writes nothing). Sets `project.outcome = "lost"`,
    `project.loss_reason = reason`.
  - `po_received`: `outcome = "won"`, `loss_reason = None`.
  - any other key: outcome and loss_reason untouched.
- **BE2 First PO.** `project_po_service._advance_to_po_received` (`:460`): when it moves the status,
  it also sets `outcome = "won"`, `loss_reason = None`. When it does not move (no edge, already
  there), outcome is untouched.
- **BE3 Mark won / Re-open.** New `POST /api/v1/projects/projects/{id}/outcome`, body
  `{"outcome": "won" | "open"}` (a new `ProjectOutcomeChangeRequest`), permission EDIT +
  `assert_can_write_project`, returns `ProjectResponse` like the status route. New service
  `project_service.set_project_outcome(db, project, *, outcome, actor_user_id, permissions)`:
  - `won`: from `open` only. From `lost`: 409 `project_lost` ("Re-open the project first.").
    From `won`: no-op, 200. Status untouched. `loss_reason = None`.
  - `open` (Re-open): from `won` or `lost`; from `open`: no-op, 200. `loss_reason = None`. If the
    project's status key is `lost`, `status_id` returns to the rung it held before Lost. As
    built: `change_status` now also writes `from_status_id` in the `stage_changed` payload, and
    Re-open prefers the `from_status_id` of the newest event into Lost; for an older event without
    it, the `to_status_id` of the newest `stage_changed` row older than that event; with neither,
    the graph's initial status (`status_service.initial_status`). This is a direct write, not a graph edge (terminal rungs
    have no outgoing edges by design, `status_service.py:374`), and it records a
    `stage_changed` event. Any other status key: status untouched.
  - Every real change records a project event, template `outcome_changed`, payload
    `{"outcome": <new>}`.
  - Any other value: 422 `project_outcome_invalid`.
- **BE4 Customer accept** (`project_quotation_document_service.py:1684`): `_win_the_scopes_on`
  goes. On accept, if `project.outcome == "open"` it becomes `won` (loss_reason None); `won` or
  `lost` is left alone. The acceptance itself is recorded either way. No area outcome is written.
- **BE5 Make quotation** (`:912`): refused with 409 `project_lost` ("This project is lost. Re-open
  it before making its quotation.") when `project.outcome == "lost"`; allowed on `open` and
  `won`. The `project_not_won` check goes. Every area of the chosen revision is copied (the
  lost-area skip goes); copies get no outcome (column default).
- **BE6 Forecast pipeline** (`project_forecast_service._open_quotation_totals`, `:139`): counts
  only projects whose `outcome == "open"`; no `ProjectQuotation.outcome` filter. For such a
  project, if it holds a quotation document (`project_quotation_document_service.project_quotation`),
  only the areas of that document count; otherwise all its areas. Each area counts its highest
  version, as today. Won or lost: 0 pipeline (Committed unchanged).
- **BE7 Loss-reasons report** (`loss_reason_counts`, `:394`): counts LOST projects
  (`Project.outcome == "lost"`, approved, this company) grouped by `Project.loss_reason`; same
  return shape.
- **BE8 PO intake ranking** (`project_po_reading.py:129-134`, `project_po_confirm.py:333-337`): the
  `_OUTCOME_RANK` goes. Candidates are the project's areas (filtered to the held quotation
  document when there is one, as today); exactly one candidate binds, two or more stays unbound
  (as a tie is today).
- **BE9 Removals.** `project_quotation_service.set_outcome`, `derive_project_outcome`,
  `sync_project_outcome`, the sync on area delete (`:486`), the route
  `POST /quotations/{id}/outcome` (`api/v1/projects/quotations.py:213`) and its request schema.
  Area serializers and response schemas stop returning `outcome`, `loss_reason`, `decided_at`.
  `GET /config/loss-reasons` stays (the Mark lost dialog reads it). The `ProjectQuotation`
  columns stay in the model and DB, unused (owner Q5: no migration).

### Frontend

- **FE1 Mark lost dialog.** A new `[projectId]/components/ProjectLossDialog.tsx` (built from
  `QuotationOutcomeDialog`'s reason picker: `SearchableSelect` over `useQuotationLossReasons`, Save
  disabled until a reason is chosen). Selecting a gear move whose `toKey === 'lost'` on the project
  page opens it instead of moving; Save calls the status change with `loss_reason`. Same on the
  pipeline board: a drop onto the Lost column opens the dialog (`PipelineClient.tsx:451`).
  `changeProjectStatus` / `useChangeProjectStatus` take an optional `lossReason`.
- **FE2 Gear items** (`ProjectDetailClient.tsx` DetailActionsMenu, `:351`): "Mark won" when
  `project.outcome === 'open'`; "Re-open" when `won` or `lost`; both only when `can_edit` and
  the project is approved (not `waiting`). Service `setProjectOutcome(projectId, outcome)` +
  hook `useSetProjectOutcome` (invalidate project + toast, extracted error on failure).
  Note: the gear menu shows only when `hasGearItems`; include these items in that count.
- **FE3 Header Won pill.** A `Badge` reading "Won" (success tone, via OutcomePill if it fits) beside
  the status pill when `outcome === 'won'` and `status_key !== 'po_received'`.
- **FE4 Removals.** Per-area pill + Record outcome in `QuotationScopesTab.tsx:97-128` (coordinate
  with #2194), the pill on the area strip in `QuotationFormClient.tsx:947`, the route folder
  `[projectId]/quotations/[quotationId]/`, `QuotationOutcomeDialog.tsx`, `setQuotationOutcome`,
  `decide` in `useQuotationMutations`, `QuotationOutcome` / `QuotationOutcomeBody` types and the
  area `outcome`/`loss_reason`/`decided_at` fields.
- **FE5 Make quotation** (`quotation-documents/actions.tsx:157`): offered when
  `projectOutcome !== 'lost'` (was `=== 'won'`).
- Project-level OutcomePill in the projects grid stays.
