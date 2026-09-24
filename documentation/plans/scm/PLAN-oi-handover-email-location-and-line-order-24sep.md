# PLAN: order inquiry handover email prints the stock location per line and sorts by AutoCount SO line sequence

Status: small fix track, building (24 Sep 2026). Issue #1166.
Domain: scm (order inquiry handover email, `order_inquiry_handover` automation).
UAC: `oi-handover-email-location-and-line-order-24sep-acceptance-criteria.md` alongside.

## Problem (measured against origin/main 319f4226c)

The handover email CS triggers with Approve / Confirm on fulfilment planning (`POST /sales-orders/{pso_id}/confirm` and the board's confirm-all, both into `ProjectSupplyService.confirm` then `ProjectOrderInquiryService.refresh_for_decision`) prints its line table in insertion order: the lines named in the confirm payload, then carried-forward lines, then still-raised amendment rows in DB row order. No ORDER BY anywhere in the chain. Owner cannot predict the order.

`order_inquiry_rows.stock_location` is already captured per queued line (`_record_handover`) but `_build_handover_context` reduces it to the subject only (one distinct location becomes `OI: <location> @ <so_list>`). The per-line dict has no location key and the r2 template body has no LOCATION cell. Owner: the location per line is "very, very important".

## Ruling (owner, 24 Sep 2026)

Sort by AutoCount SO line sequence. That is `sales_order_lines.line_no` reached from `order_inquiry_rows.so_line_id`.

## Change (one seam, no schema change)

1. `_record_handover` adds `"location": row.stock_location` (blank string when None) to the per-line dict, and carries the sort key on the queued item: `so_number`, `line_no` (from the row's `so_line_id` -> `ProjectSalesOrderLine.line_no`, None when the row has no SO line), `item_code`.
2. `_build_handover_context` sorts the queued items before building `lines`: by `so_number`, then `line_no` ascending with None last, then `item_code`. Still-raised amendment rows appended by `_append_still_raised_amendment_rows` go through the same sort (they are queued items too), so the whole table obeys one order.
3. New alembic revision `oihr_0003_location_column.py` supersedes the r2 body in place (same pattern as `oihr_0002_undone_headline.py`): the html and text bodies gain a LOCATION column right after S/O NO. Subject unchanged.
4. Nothing on the frontend.

Gotcha for the coder: `line_no` on `sales_order_lines` is the AutoCount sequence as pulled; do NOT use `FulfilmentBoardService._line_numbers` (positional renumbering used by the board when not all lines are mirrored). Read the docstring near `so_supply_decision_drafts` in `app/models/project_so.py` before writing the join.

## Tests (tester-first, in `tests/test_order_inquiry_handover_automation.py`)

- Column set now includes LOCATION in both html and text (`test_handover_r2_template_cells` and the blank-not-None test updated, not deleted).
- A three-line order confirmed with payload order [line 3, line 1, line 2] prints lines 1, 2, 3.
- Two orders in one email print grouped by S/O no, each in line_no order.
- A row without `so_line_id` sorts after the rows that have one, within its S/O.
- Location renders per line, blank when None; subject behaviour unchanged (existing subject tests keep passing).

## Out of scope

Undo email (`order_inquiry_undone`) keeps its own layout. Any change to what counts as a line.
