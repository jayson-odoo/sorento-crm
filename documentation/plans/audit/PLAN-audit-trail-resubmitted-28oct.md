# PLAN: Audit Trail shows every resubmission (AUDIT-TRAIL-RESUBMITTED)

Status: in review (small fix track: no migration, no auth/RBAC change, frontend display only)

## Journey

Owner, 28 Oct: "I can't tell Kay the audit trail is live because the audit trail hasn't been
fixed to resubmitted". A complaint rejected twice and resubmitted by the customer each time must
read Rejected -> Resubmitted -> Rejected -> Resubmitted on its Audit Trail, with the #1924 field
diff under each resubmit, for history written before #1925 as well as new resubmits.

## Cause

- `components/audit/AuditTrail.tsx` headed a row from that row alone (`isAuditResubmit`,
  `lib/audit-fields.ts`). A rejection had no heading ("update"); a past resubmit's status line
  still read "status: rejected → submitted" (`app/api/v1/audit/audit_logs.py` `_derive_description`).
- The chatbot edit-via-submit (`app/api/v1/complaints/complaints.py`, before #1925 it called
  `update_complaint`) left the status `rejected`, so its row carried only field changes and read
  as a plain "update".
- A row that does not carry the status it moved from could not be recognised.
- #1925's backfill relabels only records still sitting in `submitted`, so nothing in prod moved.

## Change (read-only, no data rewrite, no backend change)

`lib/audit-fields.ts` `auditTrailHeadings(entries)`: walks the record's own rows oldest first,
carrying the status each row left (`status`, `approval_status`, `order_status`, and the
status-engine summary for `status_id` records).

- A move into `rejected`: "Rejected by <who>".
- A move out of `rejected` into a review stage (`submitted`, `resubmitted`,
  `pending_project_sales`, `pending`, `pending_approval`, or a cleared `approval_status`):
  "Resubmitted by <who>".
- A customer save (portal contact, integration, public link; `legacy` rows: a contact id) with
  field changes while the record is rejected: "Resubmitted by <who>". History only: rows written
  before RESUBMITTED-STATUS went live (28 Oct 03:40 MYT). Since then every resubmit moves the
  status, and an n8n (integration) edit of a rejected record is not a resubmit.
- On a Resubmitted row the summary "rejected → submitted" reads "rejected → resubmitted" (what
  #1925 writes today). A named stage stays as recorded. Child rows never move the record status.

Known limits: a status-engine record reads Resubmitted only on "Rejected → Submitted" (no engine
type has another review stage after a rejection today). A rejection older than the trail's 200
newest rows can only drop a heading, never invent one.

## Review

Reviewer round 1 NOT READY: child-row test could not fail (fixed: the child moves out of rejected
and the record's own save must still read Resubmitted); pre-S0 rows carry `actor_type = legacy`,
not null (fixed); the customer-save rule would head later n8n edits (fixed: history only).

## Tests

- vitest `components/audit/AuditTrail.resubmitted.test.tsx` (10): CMP26-0219-shaped history, new
  portal resubmit, chatbot save while rejected, legacy row without old status, legacy-actor
  customer save, integration save after go-live stays update, staff edit stays update, stock inquiry stage, status-engine record, child row. Red before the fix.
- vitest `AuditTrail.diff.test.tsx`: two assertions now read "rejected → resubmitted" (owner ruling).
- pytest `tests/test_audit_trail_resubmitted.py` (2): the portal and chatbot resubmit each write
  one complaint audit row with the move out of rejected plus the changed fields (the contract the
  trail reads). These pass on main: the backend already writes that shape since #1925.
