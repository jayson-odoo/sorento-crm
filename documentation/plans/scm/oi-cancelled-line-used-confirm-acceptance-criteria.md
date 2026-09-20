# UAC - order inquiries: a cancelled line and a used row are shown as such, and purchasing confirms them

Plan: `PLAN-oi-cancelled-line-used-confirm.md`. Owner rulings 20 Sep 2026 (C1 to C4 in the plan).
Tags: `[BE]` `[FE]` `[E2E]` `[T]` `[UX]`.

## Journey

1. **Purchasing** works the Order Inquiries list every day (high frequency, dense grid). The
   "To confirm" card is their inbox: rows customer service or the system changed, waiting for
   purchasing to say "seen".
2. A sales order line is cancelled (an edit on the sales order, or AutoCount pushes the
   cancellation). Nobody tells purchasing today: the order inquiry rows of that line look like
   any other row, and an unbought one still counts in Buy.
3. With this change the system tells them, with no decision asked of anyone else: every live row
   of the cancelled line turns grey with a `cancelled` tag, drops out of Buy, and lands in To
   confirm. Purchasing ticks it (or "select all matching") and presses Confirm: "seen". The row
   stays in the list, grey and tagged, and leaves To confirm. A purchase order or shipping order
   already linked to it stays linked, for purchasing to deal with.
4. The same for a **used** row (the grey row that holds received goods after a replan): whenever
   a row becomes used, by a replan or by a sheet re-upload rebuilding it, it lands in To confirm
   once, and purchasing confirms it the same way.
5. Pressing the To confirm card a second time clears its filter, like the other three cards.
6. What each stakeholder holds at the end: purchasing has an inbox that contains every
   cancellation and every used row exactly once; customer service does nothing new; the Buy
   figure no longer counts lines nobody will buy.

Measured on the 18 Sep 2026 prod copy: 344 live rows sit on cancelled lines (340 `actioned`,
3 `raised`, 1 `placed`; 2 hold a link), 343 of them auto-acknowledged; 10 used rows, all
auto-acknowledged; SO314593 CB2828-DIY 90 and SO314594 C-FH12 364 + 364 are the owner's examples.

## Shown as cancelled (C1, C4)

- **AC-CL-1** `[BE]` The worklist row carries `line_cancelled` (true when the sales order line
  the row sits on has `line_status = cancelled`). `response_model` must not drop it: asserted on
  the route's JSON, not only the service.
- **AC-CL-2** `[FE]` A row with `line_cancelled` is greyed exactly as a used row is (the same
  row-level class), and its Qty cell shows a `cancelled` pill beside the quantity. A row that is
  both used and on a cancelled line shows both pills. No explanatory text is added to the screen.
- **AC-CL-3** `[FE][UX]` The pill is the existing worklist pill primitive, no new variant, no
  motion. At 375px and 1280px the Qty cell does not clip: quantity, pill(s) and the Was/Now icon
  fit or truncate with a title, and the column keeps an explicit `size`.
- **AC-CL-4** `[BE]` Buy excludes a row on a cancelled line: the Buy card total, the `kind = buy`
  filter and the month tabs' buy figures all agree. Purchased and Incoming still count it when
  it holds a purchase order or shipping order link.
- **AC-CL-5** `[BE]` A row on an open or closed line is unaffected in every count and filter
  (`closed` is not `cancelled`).

## Purchasing confirms a cancelled line (C1, C2)

- **AC-CL-6** `[BE]` When a sales order line goes from not cancelled to `cancelled`, by the sales
  order edit (`sales_order_service._upsert_lines`) or by the AutoCount push
  (`document_ingest_service`), every live order inquiry row of that line (state not `cancelled`,
  `actioned` included) whose `ack_state` is `acknowledged` becomes `changed` with `changed_at`
  set. A row already `awaiting`, `changed` or `rejected` is left as it is.
- **AC-CL-7** `[BE]` Only the TRANSITION flags rows: a second push of the same already cancelled
  document, or an edit that leaves a cancelled line cancelled, flags nothing, so a row purchasing
  has confirmed does not come back.
- **AC-CL-8** `[BE]` A row the sheet upload raises ONTO an already cancelled line (the fallback
  pass) is born `awaiting`, not `acknowledged`. Every other sheet row is still born acknowledged.
- **AC-CL-9** `[BE]` Confirm (the existing `POST /order-inquiries/acknowledge`, by ids and by
  "select all matching") acknowledges such a row like any other: `acknowledged`, leaves To
  confirm. Nothing else changes: state, quantity, links and claims are untouched, the row is NOT
  cancelled, `line_cancelled` stays true. An `actioned` row is accepted by BOTH paths (today the
  by-ids path answers 422 `order_inquiry_row_not_open` for it, plan 3.7); a row whose own state
  is `cancelled` is still refused by ids and skipped by filter. Permission stays `projects.order_inquiries.acknowledge`;
  a user without it gets 403.
- **AC-CL-10** `[BE]` Backfill, one migration, idempotent: every live row on a cancelled line
  that is `acknowledged` becomes `changed` with `changed_at` set (344 on the measured copy, less
  the 1 already awaiting). The statement only takes rows whose `acknowledged_at` is null or
  earlier than a fixed cutoff in the migration: run twice, the second run changes nothing, and a
  row purchasing confirmed after the first run is NOT flagged again.
- **AC-CL-11** `[BE]` The sheet rollback already keeps a row with `changed_at` set, so flagged
  rows survive a rollback and a re-upload reports them `already_raised` (asserted, not assumed).

## Purchasing confirms a used row (C3)

- **AC-CL-12** `[BE]` A replan that turns a row into a used row (`_redirect_row_if_received`)
  sets that row `changed` with `changed_at` when it was `acknowledged`.
- **AC-CL-13** `[BE]` The used row the sheet upload rebuilds (AC-RB-1 of the rebuild lane) is
  born `awaiting`.
- **AC-CL-14** `[BE]` The same backfill migration flags the used rows that are `acknowledged`
  (10 on the measured copy) `changed`, under the same run-twice rule.
- **AC-CL-15** `[BE]` A used row in To confirm is confirmed by the same route; confirming it
  moves no link and does not run the link cascade onto it (a used row is never linkable).
- **AC-CL-16** `[FE]` A used row and a cancelled-line row can be ticked and confirmed from the
  list like any row (their checkboxes are enabled; only a row whose own state is `cancelled`
  stays unselectable, as today).

## To confirm card (journey step 5)

- **AC-CL-17** `[FE]` Pressing the To confirm card while its filter is on clears the filter
  (same result as the chip's x): the chip goes, the card loses its active state, the list
  reloads unfiltered. Pressing it again sets it. Buy, Purchased and Incoming keep toggling as
  today.

## Whole journey

- **AC-CL-18** `[T]` One backend test: upload a sheet row, acknowledge, cancel its line through
  the sales order edit, read the worklist (row `line_cancelled`, in To confirm, out of Buy),
  confirm, read again (out of To confirm, still listed, still `line_cancelled`), push the same
  cancellation again (still out of To confirm).
- **AC-CL-19** `[E2E]` agent-browser evidence run on the lane stack, from the sidebar: search
  SO314593, CB2828-DIY is grey with the `cancelled` pill and sits in To confirm; tick, Confirm,
  it leaves To confirm and stays grey; the To confirm card toggles off on the second press; a
  used row is confirmed the same way. 375px and 1280px screenshots. Countdowns are never left to
  lapse, and any `email_outbox` row the run creates on the prod copy is cancelled afterwards.
- **AC-CL-20** `[T]` Existing suites stay green unchanged: `test_order_inquiry_kinds.py`,
  `test_order_inquiry_worklist.py`, `test_order_inquiry_handshake*.py`, `tests/scm/test_oi_confirm_per_so.py`,
  `test_oi_sheet_rebuild_from_planning.py` (its born-acknowledged assertions for ORDINARY rows),
  and the vitest files beside `OrderInquiriesClient.tsx`.
