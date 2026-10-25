# PLAN: DO <-> SO line links on the DO page and the SO Delivery tab (DO-SO-LINK-SURFACE)

Status: Plan (behaviour card posted as crew-ask, waiting on owner). Track: small fix (no
migration, no auth/RBAC change, no new ingest surface; expected diff under ~300 lines).

Owner ask (25 Oct): backfilling DOs from AutoCount, the DO page does not say which SO a DO
delivers, so it cannot be cross-checked. Surface the link the same way PO <-> SPO and SPO <-> GRN
already are.

## Today (main, measured)

1. **Where the link lives.** `order_lines` keeps what AutoCount sent, as sent:
   `from_doc_type`, `from_doc_no`, `from_dtl_key` (`app/models/order.py:590-592`), plus the
   resolved link `sales_order_line_id` (`app/models/order.py:567-575`). The header has its own
   `orders.sales_order_id` off `ref_doc_no` (`autocount_doc_ingest_service.py:1500-1505`).
2. **How the ingest fills it.** `_do_so_line` (`autocount_doc_ingest_service.py:925-947`): the
   exact SO line by `FromDtlKey`; else the ONE line of that product on the SO numbered
   `FromDocNo`; else no line (product on several lines, or SO not in the CRM). Never a qty or
   warehouse pick. Lines that land before their SO are re-tried on every later DO apply by
   `_fill_waiting_links` (`:1473-1498`, newest `MAX_WAITING_LINKS`). So a DO backfill fills the
   link on ingest, and re-running it (or the next push) fills the ones whose SO arrived later.
3. **DO page shows none of it.** `OrderLinesCard.tsx:154-275` columns: Product, Warehouse, Qty,
   prices, tax. `OrderLineResponse` (`app/schemas/order.py:373-383`) does not even carry
   `from_doc_no`.
4. **SO page.** Per line, the truck icon opens `SoLineHistoryBody` (DO no., date, location,
   status, actual delivery, qty) off `GET /scm/sales-orders/{id}/deliveries`
   (`app/services/scm/so_line_history.py`, SO-DELIVERIES-VIEW). The Delivery tab itself is one
   sentence (`SalesOrderDetail.tsx:2284-2314`, "8 delivered in full").
5. **The pattern to reuse** (SPO document page, `SPODocumentDetail.tsx`):
   - line column `PO` = link icon + number to the linked document (`:783-805`);
   - line column `PO (book)` = AutoCount's own source number as plain text (`:806-826`);
   - header linkage strip, `·`-separated, each a link when present, muted when not
     (`:1030-1075`);
   - several targets = `DrillTable` lightbox (`PlanRowDialog` + `DrillTable`).

Prod counts (sorento_prod_1020): NOT READ. This lane runs in a cloud sandbox with no access to
any shared DB (crew contract). Dev figures from SO-DELIVERIES-VIEW (14 Oct): of 20,154 DO lines
naming an SO, 9,828 resolve to one SO line, 4,694 to an SO + product group (several lines),
771 product not on the SO (725 are 0-qty markers), 4,861 SO not in the CRM.

## Proposed behaviour

- **R1 DO page, Lines: an `SO` column.** Link icon + SO number to `/scm/sales-orders/{id}` when
  the line's SO is in the CRM (stored `sales_order_line_id`, else the SO numbered
  `from_doc_no` in the DO's company: that number is AutoCount's explicit link, not a match).
  Plain text `from_doc_no` when the SO is not in the CRM. `-` for a line with no `FromDocNo`
  (direct DO, or a non-SO source). No line label when only the SO + product is known.
- **R2 DO page header strip** (the SPO strip's grammar): `SO <n>` links for each distinct SO the
  DO's lines name, oldest first. One DO covering several SOs shows each.
- **R3 SO Delivery tab:** the existing summary sentence, then one table of every DO line under
  this SO (the rows `/deliveries` already returns, lines + groups): DO no. (link), DO date,
  Status, SKU, Location, Actual delivery, Qty, with a total row. Same columns as
  `SoLineHistoryBody`, plus SKU. Empty: today's sentence only.
- **R4 Scope + explicit only:** reads in the DO's / SO's own company; voided and deleted DOs out
  (same filters as `so_line_history`); no name or qty matching anywhere.

## Tests (red first)

- BE: `GET /order-management/orders/{id}` lines carry `from_doc_no` and `sales_order` ref
  (stored link; SO by number; SO not in CRM; direct DO; other company's SO not resolved).
- FE: OrderLinesCard SO column three states; header strip several SOs; SO Delivery tab table
  rows + total + empty state.
