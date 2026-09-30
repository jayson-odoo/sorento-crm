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

## Server, preview (`POST .../fulfilment-planning/confirm-all` with `preview: true`)

- AC-P1 A preview press writes nothing: after it, `so_supply_decisions`, `order_inquiry_rows`,
  `stock_transfers` and `so_supply_decision_drafts` are unchanged (row counts and max ids).
- AC-P2 The preview answer per order carries the same `lines_confirmed`, `lines_carried`,
  `lines_held_back` and `lines_fulfilled_skipped` a real press would, plus `inquiry_rows`
  (verb, line_no, item_code, qty, delivery_date, stock_location, note) and `transfers`
  (kind, qty, from_location, to_location, line_no) the press would raise.
- AC-P3 A real press right after the preview, same body, writes exactly the previewed
  `lines_confirmed` and raises exactly the previewed inquiry rows and transfers.

## Board, Preview then Confirm (v2, supersedes AC-D1..D5 below, which are retired)

- AC-V1 The header shows "Preview (N)" (N = saved lines the press would send) and Confirm,
  disabled with the hint "Preview first", until a preview for the current board state has
  loaded. There is no confirm popup.
- AC-V2 Preview renders inline under the header, grouped per order: one row per previewed
  inquiry row (line, item, verb, qty, delivery date, location, the decision behind it, saved by
  whom and when). A decision saved by another planner or before this board was opened carries
  that fact in amber. Held-back and not-sent lines are listed with their reason, untickable.
- AC-V3 Every row starts ticked. Unticking removes that line from the press (its draft is left
  alone) and the Confirm label follows: "Confirm N lines". Unticking every row disables Confirm.
- AC-V4 Any change to the postable population after a preview (save, undo, board refetch that
  changes drafts) disables Confirm until Preview is pressed again; the stale preview says so.
- AC-V5 Confirm posts exactly the ticked previewed lines; results block and toast read the
  server echo (AC-R1..R4 unchanged).

## Board, pre-confirm dialog (v1, RETIRED by owner feedback 30 Sep 2026)

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
