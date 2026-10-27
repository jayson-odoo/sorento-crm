# PLAN: Audit Trail shows every field change (AUDIT-TRAIL-DIFF)

Status: in progress (small fix track: no migration, no auth/RBAC change, expected diff under ~300 lines)

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
   The per-record trail path in `audit_logs.py` passes it. Child rows render with the child's
   kind and identifying field (e.g. "Product line CWCY604 added").

## Tests

- Backend: `tests/test_audit_trail_children.py` (child row on the parent's trail, other record's
  child excluded, flag off keeps old behaviour).
- Frontend: `components/audit/AuditTrail.test.tsx` on the two resubmit shapes (status + long
  text append; status + product code), bookkeeping-only row hidden, child row line.
