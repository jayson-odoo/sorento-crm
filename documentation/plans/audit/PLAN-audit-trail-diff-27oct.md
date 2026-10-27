# PLAN: Audit Trail shows every field change (AUDIT-TRAIL-DIFF)

Status: in review (small fix track: no migration, no auth/RBAC change; about 750 changed lines, most of them tests and docs)

## Journey

Owner, 27 Oct: "in the log, i can't see what Jay changed when he resubmit?" A complaint
resubmitted from the portal changed `defect_description` (text appended) and `product_code`
alongside `status: rejected -> submitted`, and the record's Audit Trail showed only the status line.

## Cause

- `GET /api/v1/audit/` fills `description` with a status summary for any UPDATE whose `status` /
  `approval_status` / `order_status` moved (`app/api/v1/audit/audit_logs.py` `_derive_description`).
- `components/audit/AuditTrail.tsx` `collectChangeLines` renders `description` INSTEAD of the
  field diff when one is present, so every other field on the same row is hidden.
- Rows whose before/after differ only in bookkeeping columns render a bare "Updated".
- Child rows (e.g. `complaint_product_lines`, `__audit_parent__ = "complaint_id"`) are stamped
  with `root_entity_type/root_entity_id` = the complaint, but `list_audit_logs` filters on
  `entity_type/entity_id` only, so they never reach the record's trail.

## Change

1. `AuditTrail.tsx`: an UPDATE always lists its field changes, `Label: old -> new`. The derived
   description (status summary) is an extra first line, never a replacement. Bookkeeping fields
   (`updated_at`, `last_responded_at`, `portal_draft_at`, ...) are skipped through one shared
   list. Long text (over 120 chars) shows as a collapsible before/after, never silently cut.
   A row with no real change after skipping is HIDDEN (decision: a line that says "No field
   changed" is noise to the reader; the row carries nothing they can act on).
2. `list_audit_logs(include_children=True)`: with `entity_type` + `entity_id` set, also match
   rows whose `root_entity_type/root_entity_id` is the record (uses `ix_audit_logs_root_entity`).
   `GET /api/v1/audit/logs` takes it as an explicit opt-in query param (default false), sent only
   by `services/auditService.ts` (the AuditTrail reader): the Packing List Timeline and the admin
   Audit Logs screen send entity_type + entity_id too and must keep getting the record only.
   Child rows are labelled server side ("Product line CWCY604") from the newest audit row that
   carries an identifying field, else the live child row. AuditTrail reads up to 200 rows,
   since child rows now share the page.
3. Owner + Kay add-on (27 Oct ~19:31): an UPDATE moving rejected -> submitted (raw `status`,
   `approval_status`, `order_status`, or a status-engine summary "Rejected → Submitted") heads its
   row "Resubmitted by <actor>", field changes listed under it. Derived from the transition, so
   existing history reads that way with no data change. No new status (a separate lane adds one).

## Tests

- Backend: `tests/test_audit_trail_children.py` (child row on the parent's trail, other record's
  child excluded, flag off keeps old behaviour).
- Backend: also the route without the flag returns the record only, and a child named from its
  live row.
- Frontend: `components/audit/AuditTrail.diff.test.tsx` on the two resubmit shapes (status + long
  text append; status + product code), the Resubmitted heading (raw status and status engine),
  bookkeeping-only row hidden, child row lines, id-valued field, status_id under an unrelated
  description, all-hidden page.

UAC: `audit-trail-diff-acceptance-criteria.md`.
