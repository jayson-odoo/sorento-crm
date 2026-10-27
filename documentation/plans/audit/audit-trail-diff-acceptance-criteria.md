# UAC: Audit Trail shows every field change (AUDIT-TRAIL-DIFF)

Plan: `PLAN-audit-trail-diff-27oct.md`. Applies to every record page that renders the shared
`components/audit/AuditTrail.tsx` (complaint, stock inquiry, purchase request, product, sample
request, new product application, product specification).

- **AC-1** An UPDATE that moved a status AND other fields lists the status line first, then one
  line per other field, `Field label: old → new`. The status is not listed twice.
- **AC-2** A long text change (over 120 characters, or multi-line) shows as "<Field> changed",
  expandable to the full Before and full After. Nothing is cut.
- **AC-3** Bookkeeping fields (`updated_at`, `last_responded_at`, `portal_draft_at`, ...) never
  show. A row whose only change is bookkeeping is hidden. If every row on the page is hidden the
  panel reads "No field changes to show."
- **AC-4** A field holding an id reads "<Field> changed", never the id.
- **AC-5** An UPDATE moving rejected -> submitted is headed "Resubmitted by <actor>", including
  rows written before this change (no data migration).
- **AC-6** A complaint's trail shows its product lines: "Product line <code> added", "Product line
  <code> removed", "Product line <code>: Quantity: 2 → 3".
- **AC-7** The Packing List Timeline and the admin Audit Logs screen are unchanged: they do not
  receive child rows.
