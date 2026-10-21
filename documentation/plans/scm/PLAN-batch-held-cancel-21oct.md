# PLAN-BATCH-HELD-CANCEL: Confirm applies a pending AutoCount change and sends the held Cancel SO

Status: Review (small fix track, S+: no migration, no auth/RBAC change, no new ingest surface; owner P0 21 Oct)
UAC: `batch-held-cancel-21oct-acceptance-criteria.md` (alongside)
Owner ruling: (a), 21 Oct 2026 ~14:30 MYT. Supersedes AC-F11 of `PLAN-so-cancel-line.md`
("a cancel draft the pending planning change NAMES is held, not counted").

## Defect (prod 9bbb8fd7df, planning board, SO394881)

Gear > Simulate confirm: "Simulation, nothing was saved: 0 of 0 orders would confirm / SO394881: has a
saved Cancel SO that commits after the pending change is applied", one line per held line (12). The real
Confirm (10) does the same: 0 of 0. Owner evidence 15:30: the tabs read Saved (0) / All (90) while the
button reads Confirm (10). Nothing ever applies the change, so the saved Cancel SO waits forever.

## Cause (file:line at 9bbb8fd7df)

FB = `sorento_crm_frontend/app/(protected)/project-sales/_shared/lib/fulfilmentBoard.ts`,
FBP = `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/components/FulfilmentBoardPanel.tsx`,
FP = `sorento_crm_backend/app/api/v1/projects/fulfilment_planning.py`.

- SO394881 carries a PENDING AutoCount batch (dev twin a0df3624: 10 `cancelled` rows on the old lines,
  30 `added` rows for the replacement lines, all undecided). Cancel SO was saved on replacement lines.
- FE names a line through `row.project_line_id ?? row.proposal.project_line_id`
  (`boardChangeAnnotations.ts:671`), so the replacement lines are "named"; FB:364-366 turns their saved
  Cancel SO into `blocked_cancel`. The server only refuses a cancel whose line is a row's own
  `project_line_id` (FP:1411-1435): FE and BE disagree on what "named" means.
- FBP:1618-1706: the held lines go in `heldBackByBatch`; the order has no `lines`, no `cancelled_lines`,
  so FBP:1706 `continue`s - the order is never posted, the batch is never applied.
- The counter counts the 10 book-cancelled lines (`cancelled=change_row.kind == "cancelled"`,
  `project_fulfilment_board_service.py:1824`; role `cancelled`, FB:916 / FB:1069), so it offers Confirm (10)
  for a press that sends nothing. Saved reads 0 because `pressPostsContribution` (FB:434) counts neither the
  held Cancel SO nor the book-cancelled lines. The results header drops the held entry from both sides
  (FBP:2869-2871): "0 of 0".

## Design

Server facts this rests on (scout, file:line):
- `_apply_one_order` accepts only rows decided `confirm`/`amend` or of kind `cancelled`
  (`planning_change_service.py:4446-4451`); an undecided `added` row is left pending in either order.
- A live non-`cancelled` row whose core line is already cancelled is closed as superseded, "the
  sales-order line is cancelled" (`planning_change_service.py:4498-4521`).
- `cancel_lines` refuses a line the active decision covers, 409 `supply_cancel_line_covered`
  (`project_supply_service.py:1362`). Row decisions can be set ahead of the press
  (`api/v1/projects/planning_changes.py:88`), so an apply that ran first would compose a decided row's line
  and then refuse its cancel.
- A retire-only apply answers with a confirm result (`lines_decided` = retired), never a 422
  (`planning_change_service.py:4805-4826`).

1. BE (FP `_confirm_with_possible_rejects`): drop the `board_cancel_not_supported_in_batch` refusal. A saved
   Cancel SO always rides in the batch press. The one transaction keeps its order (cancel the lines, then
   apply the change for this order): the apply then closes a decided row on a cancelled line instead of
   composing it. The owner sees one press that applies the change and sends the Cancel SO; a failure rolls
   the whole order back, so the saved decisions stay saved.
2. BE: the result says whether the press applied the AutoCount change: `planning_change_applied: bool` on
   `ConfirmResult` and `ConfirmManyOrderResult` (true when the batch apply answered with a result, false when
   it had nothing to apply, e.g. every row undecided).
3. FE lib: a saved Cancel SO is never held by a pending batch (`blocked_cancel` goes); `pressPostsContribution`
   counts a book-cancelled line the press retires, so Saved (N) and Confirm (N) are the same population.
4. FE panel: `heldBackByBatch` keeps only staged rejections (the server still refuses
   `rejected_line_ids` beside a batch). The order posts `batch_id` + `cancelled_lines`.
5. FE results: an order whose press applied the change reads
   "SO394881: applied the AutoCount change; 12 lines transferred to Cancel SO" (Simulate: "would apply the
   AutoCount change; would transfer 12 lines to Cancel SO"). Header: "1 of 1 orders confirmed".

Architecture: one predicate (`pressRoleFor`) still decides count, Saved, body and dialog; the change removes a
special case (`blocked_cancel`) rather than adding one, and the server's refusal goes with it, so FE and BE no
longer hold two definitions of "named". Other class fixed by the same edit: any saved Cancel SO on an order
with a pending batch, whatever row kind names it.

## Rulings added during the lane (21 Oct 2026)

- Crew Q1 (a): a retire-only apply takes ONLY the retired lines out of the revision, through the
  same `confirm(lines=[], uncover_line_ids=..., defer_auto_place=True)` a composed press uses;
  supersede only when every covered line leaves (planning_change_service.py Q1 branch).
- Crew Q2 (a): an `added` row links to its mirror line by core line (`link_rows_to_mirror_lines`);
  an undecided row on a cancelled core line closes superseded, an undecided `added` row on a
  covered line closes applied (`_settle_answered_rows`); a row on an uncovered line stays pending.
- Crew item 3: an order whose only counted lines are book-cancelled posts its batch; a press that
  applied rows but wrote no revision answers ok (reviewer round 1).
- Owner email ruling, final (a) ~16:00 MYT: ONLY the press this fix enables is silent. When the
  press applies a pending change with a Cancel SO that change names (`_cancels_held_by_batch`),
  `QUIET_CANCELS_KEY` stops cancelled handover lines, the CANCEL list of `record_cancelled_lines`
  and changed-with-links. A normal Cancel SO (8 Oct rule, #1530) and a batch retire without held
  cancels (#1806) still email. The in-app "Planning change applied" notice stays.
- Results echo each Cancel SO line's reason ("AutoCount Cancel SO <doc>").
- Prod reach: `batch-held-cancel-21oct-prod-read.sql` (owner runs it; dev copy: 81 open batches,
  85 orders, 173 unlinked added rows, 0 held drafts).

Not in scope (follow-up issue): a staged REJECTION on a batch-named line still waits for the change to apply
(server refuses `rejected_line_ids` beside `batch_id`, FP:1398-1407). Same never-stuck class; the ruling is
about Cancel SO.

## Tests (red first)

- FE lib `fulfilmentBoard.batch-held-cancel.test.ts` (SO394881 shape: 10 book-cancelled lines, 12 batch-named
  uncovered lines with saved Cancel SO, covered rest): `cancelledLinesFor` returns the 12; `confirmSummaryFor`
  toConfirm 22 over 1 order; every one of the 22 is Saved (`pressPostsContribution`), none other is.
- FE lib `fulfilmentBoard.so-cancel-line.test.ts` AC-F11 flipped to the new rule.
- FE panel `FulfilmentBoardPanel.test.tsx`: Confirm on the shape posts `batch_id` + 12 `cancelled_lines`; the
  results read "1 of 1 orders confirmed" and "applied the AutoCount change; 12 lines transferred to Cancel
  SO"; no "commits after" text. Simulate shows the same plan with "would".
- BE `tests/test_so_cancel_line.py`: c12 flipped (a cancel the batch names rides along: line cancelled, the
  batch's `cancelled` row applied, `planning_change_applied` true); c26 asserts `planning_change_applied`
  false; a decided `added` row on the cancelled line is closed superseded, not composed.

## Rollout

No migration. Prod SO394881: one Confirm applies the change and sends the 12 Cancel SO.
