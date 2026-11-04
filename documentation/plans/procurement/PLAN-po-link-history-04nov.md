# PLAN: PO line S/O link history (lane PO-LINK-HISTORY)

Status: Build (behaviour card posted, ask out; proceeding on recommendations). Track: standard (M):
touches audit read permission (RBAC), so security-reviewer joins. Additive data migration (backfill only, no DDL).

Owner, 4 Nov 2026 (PO 202609-S0111 > Lines, 3 BRW-NTC lines showing S/O SO422492): "can i see the
audit trails of when is this linked in the UI?"

## Facts (verified at base 87a9fe4e)

- S/O column = `purchase_order_lines.from_so_line_ref` (`app/models/procurement.py:966-975`), rendered by
  `BookSoCell` (`PurchaseOrderDetail.tsx:852-864` -> `scm/components/BookSoCell.tsx:41`), number via
  `sales_orders.source_ref` (`order_link_service.py:687`).
- Only writer: the AutoCount PO ingest. `_line_values` copies it (`document_ingest_service.py:1415-1416`);
  three write sites in `_sync_lines` / `_adopt_lines`: matched-by-ref update (`:1627`, change already
  detected in memory at `:1592-1606` for `_pending_ref_moves`), new line (`:1658`), adopted pool line (`:1862`).
- Not audited: `PurchaseOrderLine.__audit_skip__` (`procurement.py:929`), `OrderLinkClaim.__audit_skip__`
  (`scm.py:1236`). `PurchaseOrder` header is not `__audit_track__`, so the sync writes no header rows either
  (`audit_service.py:106-123`).
- Explicit `log_audit` / `record()` rows are written whatever the writer (`audit_service.py:111-113`), so a
  named event is the existing mechanism; no new table.
- Per-record trail: `components/audit/AuditTrail.tsx` (fetches with `include_children=true`,
  `services/auditService.ts:16`); non-admin read is gated by `_PER_RECORD_VIEW_PERMISSION`
  (`app/api/v1/audit/audit_logs.py:27-38`), which has no `purchase_orders` entry today (admin only).
- Placed popup inquiry rows already SELECT `OrderInquiryLink.linked_at` (`purchase_order_service.py:545`) but
  do not serve it; `linked_by` / `auto` live on the link (`project_so.py:1213-1217`).
- AutoCount never sends WHO changed a link: the CRM can say only "AutoCount sync at <time>".

## Behaviour card

1. Every S/O link change the AutoCount PO sync writes on a PO line (matched update with a different ref,
   a NEW line born with a ref, an adopted line whose ref differs) writes ONE audit EVENT row:
   `event = scm.po_line.book_so_change`, entity `purchase_order_lines/<line id>`, root
   `purchase_orders/<po id>`, old/new = `{from_so_line_ref, so_number}`, description
   "<item code>: S/O <old | none> -> <new | none>". A re-push with the same ref writes nothing.
   Inside the record's savepoint, so a failed record leaves no event.
2. Backfill (data migration, idempotent): one `scm.po_line.book_so_seen` EVENT per currently linked PO line
   with no event yet, `changed_at` = the line's earliest `order_link_claim.claimed_at` (source autocount)
   else the line's `created_at`. Shown as "on or before <date>" because it is an upper bound, not the moment.
3. PO detail, Lines tab, S/O cell: the value opens a popover: "Linked by AutoCount sync on <date time>",
   "Was <previous SO | not linked>"; a backfilled one reads "Linked on or before <date>" and "Earlier history
   not recorded". A line whose latest event is an unlink shows the dash with the same popover.
4. PO detail gains a History tab (`AuditTrail`, entity `purchase_orders`), readable with
   `scm.purchase_orders.view`.
5. Placed popup: a "Linked" column on order-inquiry rows: "<user name> <date>" or "Auto <date>".

## Tests (red first)

- sync: changed ref -> 1 event with old/new; same ref -> 0; new line with ref -> 1 (old none); new line
  without ref -> 0; failed record -> 0.
- backfill: seeds one per linked line, second run seeds 0, a line with an event is skipped.
- PO detail serializer: `book_so_link` carries at / estimated / previous.
- audit read: PO-view user reads `purchase_orders` trail; user without it gets 403.
- placements: `linked_at`, `linked_by_name`, `auto` served.
- vitest: BookSoCell popover text (event, estimated, none); Placed "Linked" column; History tab renders.
