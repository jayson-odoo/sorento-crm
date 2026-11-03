# PLAN: CONFIRM-DIALOG-SPEED

Status: PR 1 #2128 merged (81d653330b). PR 2 #2141 in progress (draft): `_oi_placements` rewrite
+ `source_ref` index (cdsp_0001) built; email-line and refusal gaps from crew's pass in progress;
stock-debt "build once" measured unsafe (equivalence tests changed answers), proposed as its
own planned lane. Track: standard (migration). UAC: `confirm-dialog-speed-3nov-acceptance-criteria.md`.

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
   cells, editable and read-only rows alike (never the board's words as if they were the
   email's), and takes no line-remark typing yet; split-row remarks are the sheet's own.
   Confirm waits until every page's run has landed, under the same line. A failed run shows its
   own Retry and holds Confirm only; the sheet (and any unsaved edit) stays.
4. Opening Confirm joins a board read already in flight instead of cancelling and resending it.
5. Backend (crew profile hot spot 1): the placement pass reads each product's open PO lines and
   SPO allocations once per pass (`_document_rows_memo`, keyed by product and the session's
   company scope) instead of once per row walked.
   Skipping the pass in a dry run was considered and refused by crew ruling: keeping it keeps
   the dry run the press's own write by construction. (An "ORDER 25 vs ORDER 15" measurement
   offered as the reason was a test-session artifact, PREVIEW-EMAIL-PLANCHANGE #2135.)

Not done, on evidence: re-reading only the opened SO. The board is the selection itself and its
cells pile several orders together, so one order's read cannot be merged into it safely; PR 2
makes the read itself faster instead.

## PR 2: `_oi_placements` and the stock-debt assignments

`_oi_placements` starts from the SO lines' own order-inquiry placements and reads only the SPO
rows those name, by id, instead of one join the planner nested-looped over 1.45M
`spo_allocations` rows. Results identical: an equivalence test keeps the old statement as the
oracle. `sales_order_lines.source_ref` gets an index (cdsp_0001, CONCURRENTLY); in the sandbox
the index alone made the old statement as fast as the rewrite, so the rewrite stays only if
crew's clone measure says it still pays.

Crew pass on PR 1 (owner rule "email = preview"), folded into PR 2: (1) a page whose dry run
refuses the order shows the refusal, never board words; (2) every email line appears on the
Review split, a line the press does not cover included (read-only, the email's own words).

Stock-debt assignments "built once per request": measured and NOT done. The per-order board
service un-nets that order's holds before building, and the confirm's first build depends on
which holds are un-netted when; sharing or warming the product-keyed cache changed a covered
line's live suggestion (5 -> 20) and moved a dry run's stock-short notice. Needs the cache
keyed by its real inputs: its own lane.
