# PLAN: PO line S/O link history (lane PO-LINK-HISTORY)

Status: Review (crew answered all five card questions (a), 4 Nov; reviewer + security-reviewer fix round
landed). Track: standard (M): touches audit read permission (RBAC), so security-reviewer joined. Additive
data migration (backfill only, no DDL).

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
   with no event yet, `changed_at` = the line's earliest `order_link_claim.claimed_at` (source autocount),
   converted from Malaysian wall time to UTC (`order_link_service._now()` stamps MYT; crew pass found 22,248
   rows 8 h late before the fix), else the line's `created_at` (already UTC). Shown as "on or before <date>" because it is an upper bound, not the moment.
3. PO detail, Lines tab, S/O cell: the value opens a popover: "Linked by AutoCount sync on <date time>",
   "Was <previous SO | not linked>"; a backfilled one reads "Linked on or before <date>" and "Earlier history
   not recorded". A line whose latest event is an unlink shows the dash with the same popover.
4. PO detail gains a History tab (`AuditTrail`, entity `purchase_orders`), readable with
   `scm.purchase_orders.view` scoped to that PO (crew ruling, re-pass on 2339d063; it reversed the
   security review's move to `scm.dashboard.view`). The tab is hidden, and `?tab=history` opens General,
   for a user without it. Non-admin per-record reads get `ip_address` blanked (security review S1).
5. Placed popup: a "Linked" column on order-inquiry rows: the user's name (or "Auto") with the date and time
   beneath it; column widths sum to 1150px so the grid fits the dialog at 1280 with no inner scroll.

## Tests (red first)

- sync: changed ref -> 1 event with old/new; same ref -> 0; new line with ref -> 1 (old none); new line
  without ref -> 0; adopted import line -> 1 (old = the import's ref); failed record -> 0; dry run -> 0.
- backfill: seeds one per linked line (run with a batch of 1, so the keyset loop is walked), second run
  seeds 0, a line with an event is skipped.
- PO detail serializer: `book_so_link` carries at / estimated / previous.
- audit read: `scm.purchase_orders.view` user reads the `purchase_orders` trail (no IP); no permission or
  `scm.dashboard.view` alone gets 403; another record type 403s; another company's viewer gets nothing.
- placements: `linked_at`, `linked_by_name`, `auto` served.
- vitest: BookSoCell popover text (event, estimated, none); Placed "Linked" column; History tab renders.

## Browser evidence (sandbox stack, 4 Nov)

Cloud sandbox: backend + `next dev -H 127.0.0.1` with dev auto-login, an empty bootstrapped DB seeded with a
PO shaped like 202609-S0111 (four BRW-NTC lines: born linked, moved SO411111 -> SO422492, linked before
history (backfill ran through `alembic upgrade`), unlinked). Navigated Procurement > Supply Chain > Purchase
Orders > 202609-S0111 by sidebar clicks (after enabling the tenant's modules on the empty DB).
Screenshots in `evidence/po-link-history/`: the three popover states and the History tab at 1280, popover and
History tab at 375 (page scrollWidth 360, no horizontal scroll). History rows read "by System" there because
the seed wrote them outside an ingest request; a real push carries the integration actor. The Placed popup's
Linked column was not exercised in the browser (no order inquiry seeded); vitest + pytest cover it.
