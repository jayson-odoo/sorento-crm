# PLAN - a line AutoCount deleted tells purchasing CANCEL on the planning change Confirm

Status: IN BUILD, 20 Oct 2026. Small fix track (server only, no migration, no UI). Lane
OI-RETIRE-CANCEL-EMAIL. UAC: `oi-retire-cancel-email-acceptance-criteria.md`.

## Owner case (20 Oct 2026)

Staff deleted a line in AutoCount and added a replacement line of another product. The CRM email
on Confirm carried only ORDER for the new line, no CANCEL for the deleted one.

## Cause (origin/main 7152037ef9)

- Pull marks the deleted line `line_status = cancelled` (`document_ingest_service.py` 1631-1648);
  the diff records a `cancelled` change (`outstanding_diff.py` 238-246).
- Apply retires that line's rows in `planning_change_service._retire_inquiry_rows` (3928) BEFORE the
  confirm on purpose (4658-4675), so `_retire_uncovered_rows` (which queues the CANCEL handover,
  `project_order_inquiry_service.py` 5813/5830) never sees them. `_retire_inquiry_rows` never calls
  `_record_handover`, so no CANCEL line reaches the email; purchasing gets only an in-app notice
  (`_notify_purchasing`, `send_email=False`).

## Fix

`_retire_inquiry_rows` queues `_record_handover(kind="cancelled", was={"qty": ...})` for every row
it cancels, and ALSO for an `actioned` row it leaves standing (that row is a person's word, so it
stays live, but purchasing still has to hear the line is gone; never a silent keep). The line rides
the same commit's handover email as the confirm's ORDER lines. No duplicate: `_retire_uncovered_rows`
only reads raised / partly linked / placed rows, which this apply has already cancelled, and never
reads `actioned` rows.

## Exposure query (read-only, for the owner to run on prod)

Every Buy row a `cancelled` planning change retired since 19 Oct 2026 00:00 MYT. Before this fix
no path queued a handover line for these rows, so each one is a CANCEL purchasing never got by
email. Evidence:

- `audit_logs` (`models/audit.py` 34; `entity_type` 37, `entity_id` 42, `action` 45, `changed_at`
  53 (`clock_timestamp()`, session time zone), `new_values` 55, `event` 88): `_record_cancel`
  writes `entity_type = 'project_order_inquiry_rows'`, `action = 'EVENT'`,
  `event = 'OI_ROW_CANCELLED'`, `new_values.cause` (`project_order_inquiry_service.py`
  1203-1212); `_retire_inquiry_rows` passes cause `planning_change_retired`
  (`planning_change_service.py` 3987).
- `projects.order_inquiry_rows` (`models/project_so.py` 1002; `order_inquiry_id` 1008,
  `so_line_id` 1011, `item_code` 1015, `qty` 1016, `verb` 1019, `note` 1056, `state` 1067):
  verbs ORDER / ORDER_BACK / RESERVE_AND_ORDER (784, 785, 809), states `actioned` / `cancelled`
  (739, 740).
- `actioned` rows get no audit row, only the note `The line was closed by a planning change
  batch.` (`planning_change_service.py` 4697), found through `projects.planning_change_rows`
  (`models/planning_change.py` 132; `batch_id` 138, `project_line_id` 146, `kind` 158 =
  `cancelled` via `_map_kind` (`planning_change_service.py` 795), `applied_state` 192 =
  `applied` (62), `created_at` 201) and `projects.planning_change_batches` (92, `applied_at` 109,
  `datetime.utcnow()` at `planning_change_service.py` 5203).
- `projects.order_inquiries` (`models/project_so.py` 822, `project_sales_order_id` 839),
  `projects.sales_orders` (449, `autocount_doc_no` 478), `projects.sales_order_lines` (527,
  `line_no` 547).

```sql
-- READ ONLY. Lines since 2026-10-19 00:00 MYT where a 'cancelled' planning change retired a
-- Buy OI row and no CANCEL reached the handover email.
WITH bound AS (
  SELECT timestamptz '2026-10-19 00:00:00+08' AS t
), cancelled_rows AS (
  SELECT a.entity_id::uuid AS row_id, a.changed_at AS told_at, 'cancelled' AS how
  FROM audit_logs a, bound
  WHERE a.entity_type = 'project_order_inquiry_rows'
    AND a.action = 'EVENT'
    AND a.event = 'OI_ROW_CANCELLED'
    AND a.new_values->>'cause' = 'planning_change_retired'
    AND a.changed_at >= (bound.t AT TIME ZONE current_setting('TimeZone'))
), actioned_rows AS (
  SELECT DISTINCT r.id AS row_id,
         COALESCE(b.applied_at, pcr.created_at) AS told_at, 'actioned (kept live)' AS how
  FROM projects.order_inquiry_rows r
  JOIN projects.planning_change_rows pcr
    ON pcr.project_line_id = r.so_line_id AND pcr.kind = 'cancelled'
   AND pcr.applied_state = 'applied'
  JOIN projects.planning_change_batches b ON b.id = pcr.batch_id, bound
  WHERE r.state = 'actioned'
    AND r.note LIKE '%The line was closed by a planning change batch.%'
    AND COALESCE(b.applied_at, pcr.created_at) >= (bound.t AT TIME ZONE 'UTC')
)
SELECT so.autocount_doc_no AS so_number, l.line_no, r.item_code, r.qty, r.verb, r.state,
       x.how, x.told_at
FROM (SELECT * FROM cancelled_rows UNION ALL SELECT * FROM actioned_rows) x
JOIN projects.order_inquiry_rows r ON r.id = x.row_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
LEFT JOIN projects.sales_orders so ON so.id = oi.project_sales_order_id
LEFT JOIN projects.sales_order_lines l ON l.id = r.so_line_id
WHERE r.verb IN ('ORDER', 'ORDER_BACK', 'RESERVE_AND_ORDER')
ORDER BY x.told_at, so.autocount_doc_no, l.line_no;
```
