# PLAN: Order Request slice 2 (line history lightbox, one shared link column, purchasing sees the approved qty)

Status: behaviour card filed, waiting on crew's answers. Track: to be set after answers (expected M, no migration).
Base: PR #2381 head 1fe5a8fa (Order Request, merge go 14 Nov). Owner comments 14 Nov ~09:00.

## Facts from the code (read before deciding)

- An approved order request stays the SAME `OrderInquiry` record: same id, same OR- number. `approve()` sets
  `state = raised` on the header and on rows with qty above 0, cancels rows at 0, and adds an `OrderInquiryRaise`
  (`sorento_crm_backend/app/services/spare_part_request_service.py:1092-1156`). Purchasing opens it on the Order
  Inquiries page (`/project-sales/order-inquiries/{id}`); the requester and approver open it on the Order Request
  page (`/procurement-management/spare-part-requests/{id}`). Two pages, one record.
- The inline "was" mark is `WasMark` (`.../order-inquiries/[id]/components/orderInquiryHeaderLinesColumns.tsx:538`),
  rendered under Qty (:669) and Unit price (:700) from `submitted_qty` / `submitted_unit_price`
  (`OrderInquiryRow.requested_qty` / `requested_unit_price`, labelled at `order_inquiry_worklist_service.py:1073`).
  It shows on BOTH pages, purchasing's included.
- A per-line history lightbox already exists: `OrderInquiryLineHistoryDialog.tsx` (same folder), opened from
  `SparePartRequestRecord.tsx:172,206` and `OrderInquiryDetail.tsx:483`. Its entries come from
  `lineHistoryEntries` (`_shared/lib/orderInquiryLineFold.ts:341`, reads `previous_qty`) plus the SO decision trail.
  The approver's edits are already in History as `SPR_LINE_CHANGED` audit rows with old -> new, who and when.
- SO <-> OI links are two separate columns today, no shared builder:
  SO lines `order_inquiry` column (`scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1376`, cell
  `SoLineOrderInquiryCell.tsx:84-90,146`, link `/project-sales/order-inquiries/{id}?row={rowId}`);
  OI lines "No." column (`orderInquiryHeaderLinesColumns.tsx:863-888`, `orderInquirySoLineHref`
  `_shared/lib/orderInquiryWorklist.ts:126`, link `/scm/sales-orders/{id}?tab=lines&line={lineId}`).
- A qty change on an OI row AFTER it was raised is already stamped as `OrderInquiryRow.previous_qty`
  (`app/models/project_so.py:1171`; stamped in `project_order_inquiry_service.py` settle / cut / date-move paths) and
  shown as "Was n." in the line history dialog (`orderInquiryLineFold.ts:337-362`).
- Today an order request can change after approval only through **Revise** (requester, until purchasing acknowledges
  a line): it goes back to Draft, leaves purchasing's list, and is approved again.

## Behaviour card

### (1) Approver changes a quantity: no inline "was"; a history icon opens a lightbox
- The Qty and Unit price cells show one value on one line. No "was ..." under it, on either page.
- A line whose qty, unit price or photos were changed after submit shows a small history icon beside the value.
  Click opens the existing line history lightbox (`OrderInquiryLineHistoryDialog`) with one row per change:
  **Field | Was | Now | By | When** (e.g. "Qty | 10 | 6 | Approver B | 14/11/2026, 9:12 am").
- Source: the request's own History rows for that line (`SPR_LINE_CHANGED`, old -> new, actor, time). Nothing new
  is stored.
- Prices follow the existing price rule: a reader who may not see prices sees "hidden" for Unit price rows.

### (2) One shared link column between documents
- One shared column builder, `documentLinkColumn`, renders "number / line" as a link and is used by:
  - SO lines: "Order inquiry" -> the OI line (today's `SoLineOrderInquiryCell`, same output);
  - OI lines from a sales order: "Sales order" -> the SO line (today's "No." link);
  - OI lines from an order request: "Order request" -> the order request page, that line;
  - Order request lines, once approved: "Order inquiry" -> purchasing's OI page, that line.
- Because the order request and its OI are one record, both links show the same OR- number and line no; the column
  name says which page it opens.
- Before approval (Draft / Pending / Rejected) the order request line's "Order inquiry" cell is "-".

### (3) Purchasing sees only the approved qty
- On the OI page (purchasing's view) an order request line shows the approved qty and approved unit price only. The
  submitted values and the approver's edits never show there (no "was", no icon for them).
- The OI line shows a change only when the qty changes AFTER approval: the request is revised and approved again
  with a different qty. Then the row gets `previous_qty` = the earlier approved qty, and the OI line's history icon
  shows "Qty | 100 | 200 | Approver B | when" (the existing post-raise mechanism).

### (4) What History means on each page
- **Order Request page, History tab** (and a Sales Order's own History): the life of the document as its owners see
  it: created, requester edits, submitted, each approver change (old -> new), approved / rejected, revised, raised to
  purchasing, and purchasing's later moves on it (acknowledged, PO linked, line rejected, cancelled).
- **Order Inquiries page (purchasing), History tab**: only what happened from the moment it reached purchasing:
  raised, acknowledged / confirmed, PO linked, line rejected or cancelled, and qty changes after approval (re-approval
  after a revise). Pre-approval edits and the approval chain do not show there.

## Examples (crew test copy, fake fixture users and numbers)

1. OR-2611-0003: Requester A submits ZZX-100 qty 10, ZZX-220 unit price 35.00. Approver B changes qty to 6 and price
   to 32.00 and approves. Order Request page: Qty "6" with a history icon -> "Qty | 10 | 6 | Approver B | ...",
   "Unit price | 35.00 | 32.00 | ...". Purchasing's OI page: Qty "6", Unit price "32.00", no icon, no "was".
   Order request line "Order inquiry" = "OR-2611-0003 / 1" -> purchasing's page; OI line "Order request" = same,
   -> the order request page.
2. OR-2611-0004: approved with no approver change. No history icons anywhere. Links as in example 1.
3. OR-2611-0005 (to create): approved at qty 100, requester revises before purchasing acknowledges, changes to 200,
   Approver B approves again. OI page: Qty "200" with a history icon -> "Qty | 100 | 200 | Approver B | ...".
   Order Request History lists the revise, the edit and the second approval; OI History lists the first raise, the
   qty change 100 -> 200 and the second raise.
4. A sales-order OI (e.g. OI-2611-0089): unchanged behaviour; the SO "Order inquiry" and OI "Sales order" link
   cells now come from the same shared column.

## Edge cases

- Approver sets qty to 0: the line is cancelled on approval (today's rule); its history icon still opens
  "Qty | 10 | 0 | ...". It does not reach purchasing.
- Approver changes a photo only: the icon shows "Photo | - | added photo.png | ...".
- A line changed and changed back (10 -> 6 -> 10): the icon still shows (two rows of history), the value reads 10.
- Rejected then resubmitted: the icon lists every change across rounds, newest first.
- Revise after purchasing acknowledged a line: still not allowed (today's rule), so no post-acknowledge qty change.
- Prices hidden for a reader: the lightbox shows "hidden" for Unit price rows (existing price rule).

## Questions for the owner (each with a recommendation)

1. **History icon visibility.** (a) only on lines that changed; (b) on every line. Recommendation: (a), the
   standing rule "default view minimal, no extra visible icons" and nothing to show on an unchanged line.
2. **Link column label when both ends are the same record.** (a) "OR-2611-0003 / 1" on both pages, the column name
   saying which page it opens ("Order inquiry" / "Order request"); (b) a plain "Open in Order Inquiries" link.
   Recommendation: (a), the same number + line pattern as SO <-> OI, which is what you asked to standardise.
3. **Purchasing and the unit price.** Purchasing sees the approved unit price only (no submitted price, no approver
   price history). Recommendation: yes, same as qty; the price history stays on the Order Request page.
4. **Changing qty after approval.** (a) only through Revise + approval again (today, blocked once purchasing
   acknowledges); (b) let the approver edit a raised line directly. Recommendation: (a), every post-approval change
   then goes through the same approver and shows on the OI as "Qty | 100 | 200".
5. **Order Request History after approval.** (a) keep showing purchasing's later moves there too (acknowledged, PO
   linked) so the requester can follow progress; (b) stop at "raised to purchasing". Recommendation: (a).

## Mock

None: the screens keep their layout; the changes are one icon in an existing cell, the existing lightbox, and a link
column built from existing cells.

## Standing rules that apply

One line per row; one value per column; default view minimal; details in a centred lightbox; History via the shared
history component (who, when, old -> new); dates dd/mm/yyyy; plain words; reuse functions (one shared link column).
