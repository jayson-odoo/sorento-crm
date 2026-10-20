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
