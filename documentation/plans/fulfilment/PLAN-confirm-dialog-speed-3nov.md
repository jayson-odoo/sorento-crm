# PLAN: CONFIRM-DIALOG-SPEED

Status: in review, PR 1 #2128. Track: standard (the diff passes ~300 lines, mostly tests; no
migration, no auth/RBAC change). PR 2 (`_oi_placements` and the confirm-all hot spots crew profiles) follows from main
after PR 1 merges. UAC: `confirm-dialog-speed-3nov-acceptance-criteria.md`.

Owner report (3 Nov 13:15): Fulfilment Planning -> Confirm SO423361 sits on the Review split
skeleton for a very long time on prod. Prod request log (3 Nov 12:50-13:32 MYT): POST
`confirm-all` 36-46 s, GET `board` 6-8 s typical, 20 s worst. New since #2091
(CONFIRM-PREVIEW-STALE): openGuide re-read the whole board, then the Review split waited on the
confirm-all dry run as well, in series.

## PR 1: the dialog stops waiting, and the placement pass gets cheap

1. The Review split waits for the board re-read and the order's split read only, never for the
   email dry run. Next is usable while the dry run is out.
2. Every page's email dry run is planned as the guide opens, on the decisions the tab holds,
   beside the board re-read, and runs one at a time in page order (crew ruling S2). Paging never
   cancels a run. A page's run is replaced only when its key moves: its body, or a save made on
   that page (the body carries no split rows), or its Retry.
3. A page whose email words have not landed prints "Preparing email preview..." in its REMARK
   cells (never the board's words as if they were the email's) and takes no remark typing yet.
   Confirm waits until every page's run has landed, under the same line. A failed run shows its
   own Retry and holds Confirm only; the sheet (and any unsaved edit) stays.
4. Opening Confirm joins a board read already in flight instead of cancelling and resending it.
5. Backend (crew profile hot spot 1): the placement pass reads each product's open PO lines and
   SPO allocations once per pass (`_document_rows_memo`) instead of once per row walked.
   Skipping the pass in a dry run was measured and refused: on the planning-change path the
   email REMARK changes without it ("ADVANCE, ORDER 15" against the press's "ADVANCE, ORDER 25").

Not done, on evidence: re-reading only the opened SO. The board is the selection itself and its
cells pile several orders together, so one order's read cannot be merged into it safely; PR 2
makes the read itself faster instead.

## PR 2: `_oi_placements` and the stock-debt assignments

`_oi_placements` starts from the SO lines' own order-inquiry placements and reads only the SPO
rows those name, by id, instead of one join the planner nested-looped over 1.45M
`spo_allocations` rows. Results identical: an equivalence test keeps the old statement as the
oracle. Stock-debt assignments are built once per request for every product it needs (board:
one shared service across `_suggest_live_for_covered`; confirm-all: all products gathered up
front), with a multi-order equivalence test so a later order still sees what an earlier one held
(plan rule R21).
