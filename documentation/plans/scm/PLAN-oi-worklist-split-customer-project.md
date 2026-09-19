# PLAN: Order inquiry worklist feedback 18 Sep: Customer + Project columns, raise history, Unconfirm

Status: in review (18 Sep 2026). Track: small fix.
Owner, 18 Sep: "here need to split the customer and project out" on the purchasing
worklist (`/project-sales/order-inquiries`), where one column reads
`ESTYLO SDN BHD (PROJECT-CASH)`.

## Today

`order_inquiry_worklist_service.py` composes `project_customer` through
`project_customer_label(customer_name, project_title, is_pre_order)` and the FE column
`project_customer` (orderInquiryWorklistColumns.tsx ~line 444) prints it. The query already
selects `customer_name` and `project_title` as labelled columns; the pre-order note is
appended by the label helper.

## Fix

Backend (`order_inquiry_worklist_service.py` + `schemas/project_order_inquiry.py`
worklist row schema):
- Row dict gains `customer_name` and `project_title` (project_title carries the pre-order
  note exactly as the helper appends it today, so nothing is lost).
- Sort map gains `customer_name` -> `_CUSTOMER_NAME`, `project_title` -> `Project.project_title`.
- `project_customer` STAYS on the row: the Excel export and search still use it. Nothing
  else about the query changes.

Frontend (`orderInquiryWorklistColumns.tsx`):
- The `project_customer` column becomes two: `Customer` (`customer_name`) then `Project`
  (`project_title`), same position, both sortable, truncate + title, explicit size.
- Column-config listing key unchanged; a stored preference naming `project_customer` just
  stops matching (hook already ignores unknown ids).

Out of scope: the per-project inquiry screen keeps its combined column (not what the owner
pointed at); the Excel export keeps its one column.

## Tests

- pytest `tests/scm/test_oi_worklist_customer_project_split.py`: worklist row carries
  `customer_name` and `project_title`; a pre-order row's `project_title` carries the note;
  `sort=customer_name` orders by customer; both fields declared on the response schema
  (response_model drops undeclared fields).
- vitest `orderInquiryWorklistColumns` or the client test: two headers Customer and Project,
  no Project / customer header.

## Slice 2 (added 18 Sep, owner ask): Raised at history tooltip

On a re-confirm every carried line gets a NEW row (the old one cancelled, "superseded by
revision N"), so Raised at jumps to the re-confirm time and the first raise survives only on
the cancelled row. The worklist row gains `raise_history`: the CANCELLED rows in the same order
inquiry with the same `so_line_id`, created before this row, newest first, each with its own
raiser (same coalesce rule as the Raised by column). Cancelled-only is load-bearing (review
round 1, blocker B1): an open sibling row on the same line is a second LIVE instruction, not a
superseded one - the unfiltered version marked 168 live duplicates as history against 1 genuine
supersede on a look at prod data. One correlated `json_agg` subquery in the existing select,
never N+1; `[]` when there is none, and the Excel export uses a separate `_EXPORT_COLUMNS`
(review round 1, S2) that drops the label outright rather than paying for the `json_agg` on
every row of the unpaged set. FE: an info icon after the date only when history exists; tooltip
"Previously raised", one line per entry.

Tests: `tests/scm/test_oi_worklist_raise_history.py` (a carried line's CANCELLED predecessor
shows in the history; an earlier OPEN sibling row on the same line does not; fresh row `[]`;
field on the schema; export headings unchanged; the export query does not select
`raise_history`); vitest icon present / absent.

## Slice 3 (added 18 Sep, owner ask): Unconfirm (N)

No path flipped a Confirmed row back to To confirm by hand (Confirm -> acknowledged, Reject ->
rejected, a raise or CS change -> awaiting). New `POST /order-inquiries/unacknowledge`, same
`ACKNOWLEDGE` permission as the acknowledge route, body `{row_ids}` only. Service
`unacknowledge_rows`: a row currently acknowledged or changed goes to awaiting with
`ack_state`/`acknowledged_by`/`acknowledged_at` cleared - `changed_at` STAYS (review round 1
ruling): it is the Was/Now audit trail `_settle_row_in_place` reads and `_handshake_for_raise`
carries across a carry, not a stamp of Unconfirm's own. A CANCELLED row (review round 1, S1) and
anything else not acknowledged/changed (awaiting, rejected, out of scope) is counted in
`skipped`, never an error. No cascade, no email. `OrderInquiryRow` carries no `__audit_track__`,
so this writes its own `log_audit` entry, one per batch, naming the actor and the row ids moved
(review round 1, security item d). FE: `Unconfirm (N)` in the worklist Actions menu beside
Reject / Upload purchase orders, ticked rows only (excluding a cancelled row even if ticked),
disabled at 0, no dialog (Confirm undoes it), toast "N rows back to To confirm", same
invalidations as Confirm.

Tests: `tests/scm/test_oi_unconfirm.py` (acknowledged and changed -> awaiting with `changed_at`
untouched; a cancelled acknowledged row skipped and untouched; awaiting / rejected skipped;
mixed batch counts; 403 without the grant; another company's row skipped untouched; an
audit_logs entry is written naming the actor and the row); vitest menu item count, service call
with the eligible ids, hidden without the grant.
