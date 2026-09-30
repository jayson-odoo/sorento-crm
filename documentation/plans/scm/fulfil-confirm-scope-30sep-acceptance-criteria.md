# UAC: Fulfilment planning Confirm posts what the planner ticked, and says exactly what it wrote

Plan: `PLAN-fulfil-confirm-scope-30sep.md`

## Server, `POST /api/v1/project-sales/sales-orders/{pso_id}/confirm` and `.../fulfilment-planning/confirm-all`

- AC-S1 A press naming lines X and Y on an order whose active revision covers lines P and Q
  answers with `lines_confirmed` = exactly `[X, Y]` (each `{project_line_id, line_no,
  item_code}`, payload order) and `lines_carried` = 2. Both fields survive `response_model`
  on both routes (the per-order entry of `confirm-all` carries the same two fields).
- AC-S2 A held-back line (#1362) is absent from `lines_confirmed` and present in
  `lines_held_back`; `lines_confirmed.length + lines_held_back.length` = lines named.
- AC-S3 A press whose named lines were all already fulfilled (`revision_no: null`) answers
  `lines_confirmed: []`; a withdrawal-only press answers `lines_confirmed: []`.
- AC-S4 `lines_decided` still equals `lines_confirmed.length + lines_carried`.

## Board, pre-confirm dialog

- AC-D1 Pressing "Confirm (N)" opens the dialog listing N rows grouped by sales order:
  "line <no> <item> · <Approved|Amended|Rejected> · <composition> · saved by <name>
  <relative time>". N in the title, the rows and the button count agree.
- AC-D2 A row saved by another user, or saved before this board was opened, carries an
  amber note "saved by <name>, <relative time>" (SO402757 line 8: "saved by Jayson
  Foundryx, 8 days ago").
- AC-D3 Every row starts ticked. Unticking a row lowers the button count and removes that
  line from the request body; its draft is untouched after the press (still Saved on the
  board). Unticking every row disables the button.
- AC-D4 Lines the press cannot post are listed under "Not posted" with their existing
  reason (suggestion changed / left out / staged rejection held by pending change), not
  counted, not tickable.
- AC-D5 An `approved` draft row shows the composition that WILL be posted (the live
  suggestion), e.g. "Borrow 43 + 57 from BRW-BB", so a changed suggestion is visible.

## Board, after the press

- AC-R1 The success toast's "N lines confirmed" equals the sum of the server's
  `lines_confirmed.length` over ok orders (a server answer without the field falls back to
  the posted count, and the results block says the server did not name its lines).
- AC-R2 The results block lists, under each ok order, the confirmed lines as
  "line <no> <item>" and "K carried forward"; held back / fulfilled / landed notices as today.
- AC-R3 When an order's posted lines differ from its echoed lines, the block shows an amber
  line "Posted P, server confirmed C: <missing lines>".
- AC-R4 Drafts are cleared locally only for lines the server echoed as confirmed.

## Board list, selection

- AC-L1 The board list's header tick box ticks every row across every page ("Select all
  rows"); the Decide chip reads "<total> selected". Other listings keep the page-only box.

## Hand test (owner, crew test copy)

- HT-A `?orders=SO402757`: with Jayson's 22 Sep draft still on line 8, tick lines 6 and 9,
  Decide -> Buy, Confirm: the dialog lists line 8 SRTSH1040 with "saved by Jayson Foundryx"
  in amber; untick it; the button reads "Confirm 2 lines"; after the press the toast reads
  "2 lines confirmed", the results block lists line 6 and line 9 and "4 carried forward", no
  transfer is proposed, and line 8 still shows Saved.
- HT-B `?orders=SO423409`: header tick box ticks all 8 remaining rows, Decide -> Buy, Confirm:
  the dialog lists 8 rows; the results block lists the 8 lines the server confirmed and
  "8 carried forward"; any line the server held back is named beside the posted count.
