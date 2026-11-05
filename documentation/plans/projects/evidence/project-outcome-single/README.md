# PROJECT-OUTCOME-SINGLE browser evidence

Run on head 54f2a6b2, headless agent-browser (session `poc-outcome`), dev server :3000,
backend :8000 on `.env.ci-tests`, empty DB seeded with: one superadmin user, the default project
funnel (`project_seed_service`), the full_suite module bundle, two approved projects
(Browse Outcome Alpha with an issued proposal, Browse Outcome Beta). Navigation was by sidebar
click (Project Sales > Projects) then card / tab clicks. One reload of the Alpha page by URL was
used after an SQL arrange step (status set to Spec In so a non-initial rung could be tested).

| Check | Result | Evidence |
| --- | --- | --- |
| (a) gear shows Mark won on an open project; Mark won adds the Won pill, stage stays Registered; POST `/project-sales/projects/{id}/outcome` 200 | PASS | 01, 02 |
| (b) Re-open removes the Won pill | PASS | 03 |
| (c) Mark lost opens the reason dialog; Save disabled until a reason is picked; Save moves the stage to Lost (POST `/status` 200, DB `outcome=lost`, `loss_reason=price`); no status POST before Save | PASS | 04, 05, 06 |
| (d) Re-open from Lost restores the previous rung: Registered (initial) and, with history, Quoted (Quoted > Lost > Re-open gave `quoted`, DB `outcome=open`, `loss_reason` null) | PASS | 07, 08 |
| (e) proposal Lines tab shows no area outcome pill or "Record outcome"; "Make quotation" is in the proposal gear on an open project | PASS | 09, 10 |
| (f) board: dropping a card on the Lost column opens the dialog | FAIL | 11 |
| (g) Mark lost dialog usable at 1280 (centred, 416 to 864) and 375 (full width, no horizontal overflow, controls inside the viewport) | PASS | 04, 12 |

## Defects

1. **(f) The board's Lost dialog is mounted inside the Filters popover.**
   `sorento_crm_frontend/app/(protected)/project-sales/pipeline/components/PipelineClient.tsx:335`
   renders `{losingTo && <ProjectLossDialog .../>}` inside the `filterContent` constant (defined at
   line 245, rendered at lines 429 and 486). `onMove` does set `losingTo` (line 462), but the dialog
   only exists while the Filters dropdown is open. Dropping a card on Lost with Filters closed does
   nothing visible and sends no request. With Filters open the dialog appears (screenshot 11).
   The dialog needs to be rendered at the top level of the component, next to the board.
   Drag was driven with native DragEvents (the board uses HTML5 draggable); a drop on Dormant
   confirmed the same path does send POST `/status`.
2. Minor: `ProjectLossDialog.tsx:37` has a `DialogContent` with no `DialogDescription`, which logs
   "Missing `Description` or `aria-describedby`" in the console on every open.

No page errors (`errors` empty). Console otherwise shows only a tiptap duplicate-extension warning
that is not from this lane.
