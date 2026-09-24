# UAC: order inquiry handover email, location column + AutoCount line order (#1166)

Plan: `PLAN-oi-handover-email-location-and-line-order-24sep.md`. Small fix track.

- AC-1 Every line in the handover email (html and text) shows LOCATION, sourced from `order_inquiry_rows.stock_location`, right after S/O NO. Blank cell when the row has no location, never "None".
- AC-2 Lines are ordered by S/O no, then AutoCount SO line sequence (`sales_order_lines.line_no` via `so_line_id`), then item code. The order CS ticked lines in, and whether a line was checked or carried forward, has no effect on the printed order.
- AC-3 Rows with no `so_line_id` (amendment rows) print after the rows of the same S/O that have one, in item code order.
- AC-4 The subject rule is unchanged: one distinct location across the email gives `OI: <location> @ <so_list>`, otherwise `OI: <so_list>`.
- AC-5 Existing handover tests keep passing after their column-set assertions are updated; no test is deleted.
- AC-6 The undo email (`order_inquiry_undone`) is byte-for-byte unchanged.
- AC-7 One new alembic revision, single head, `./scripts/alembic-reparent.sh` run before the PR, no em-dash or en-dash anywhere in the diff.
