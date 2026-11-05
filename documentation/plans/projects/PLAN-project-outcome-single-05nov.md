# PLAN: One Won/Lost outcome per project (drop per-area outcome)

Status: Plan, behaviour card posted as crew-ask on PR #2197, waiting for owner answers.
Track: standard (touches forecast, PO intake and the customer accept path; no migration if Q5 = keep).

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
6. Make quotation: still needs the project Won; copies every area of the chosen revision.
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

Questions: see the crew-ask comment on PR #2197 (copied below once answered).

## Steps (after answers)
1. Tester: red pytest for rules 2-8 + vitest for the gear items / dialog / removed pills.
2. Coder: BE (status hook, mark won/re-open endpoints, forecast, make quotation, PO ranking,
   accept path, remove W1/W2), FE (gear items, dialog, pill removal, delete FE2).
3. Reviewer + kill test; cloud browser pass; hand-test script; guide update.
