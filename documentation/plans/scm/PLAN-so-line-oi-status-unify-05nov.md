# PLAN: SO line Order inquiry status unified with the OI row (SO-LINE-OI-STATUS-UNIFY)

Status: implemented, waiting on owner hand test (PR #2187). Track: small fix track (no migration, no permission change). The SO detail, gated on SCM view, now carries a trimmed copy of each line's OI rows; see review S2 below.

## Owner ask (5 Nov 2026, ~11:05 MYT)

The Sales Order Lines tab "Order inquiry" column reads "To Buy" / "On PO/SPO" while the same
line on the OI Lines tab reads "To order". From the SO he wants: the same status as the OI row,
the linked PO / SPO numbers when bought, "Reserved from <source>" when reserved, "Rejected" plus
reason when rejected.

## Diagnosis (read-only, file:line on main 8cc55cdb)

Two readers, two different fields, two different row choices:

| | SO line "Order inquiry" | OI Lines tab "State" |
|---|---|---|
| Rows considered | EVERY row on the line, incl. cancelled and used (`redirected_to_pool`) rows: `sorento_crm_backend/app/services/scm/sales_order_service.py:710-730` | live rows only (`isLiveInquiryRow`, `_shared/lib/orderInquiryLineFold.ts:71`) |
| Which row | the NEWEST row (last writer wins, `sales_order_service.py:731-739`) | the most urgent live buy row (`pickPrimary`, `orderInquiryLineFold.ts:103`) |
| Field | `OrderInquiryRow.state` (supply cover: raised / partly_linked / placed) | `ack_state` (purchasing handshake) via `ackStatusText` (`_shared/lib/orderInquiryAck.ts:27-32`, `:70`), rendered at `order-inquiries/[id]/components/orderInquiryHeaderLinesColumns.tsx:865-872` |
| Words | `STATE_LABEL` (`_shared/components/OrderInquiryVerbPill.tsx:98-104`): raised "To buy", placed "On PO/SPO"; the pill base is `capitalize` (`lib/status-pill.ts:104`) so "To buy" prints "To Buy" | `ACK_LABELS`: awaiting/changed "To order", acknowledged "Done", rejected "Rejected" |
| Rejected | only via `FulfilmentBoardService.open_refusals` override (`sales_order_service.py:745-757`) | ack_state rejected on the primary |
| Rendered | `scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1394-1401` | as above |

So "To Buy" vs "To order" is a vocabulary split (state vs ack), and CKSW015 "On PO/SPO" vs
"To order" means the SO reader picked a row whose `state = 'placed'` while the OI page's primary
live row has `ack_state = 'awaiting'`. Two ways that happens, the SQL below says which:
(a) the newest row is a used (`redirected_to_pool`) or cancelled row that still carries
`state = 'placed'` (the OI page hides it, the SO does not), or (b) the live row has a link
(`state = 'placed'`) but purchasing has not confirmed it (`ack_state = 'awaiting'`). In both
cases the SO reader is the one out of line: it ignores the one row visibility rule
(`oi_row_visibility.is_live_row`) and reads the cover field the OI page no longer shows as the
status since OI-AUTO-CONFIRM.

## Read-only SQL (DBeaver)

```sql
-- Every OI row behind SO429216's lines, newest last (the SO reader's "last writer").
SELECT sol.line_no, r.item_code, oi.inquiry_no, r.id AS row_id, r.verb, r.qty,
       r.state, r.ack_state, r.redirected_to_pool, r.rejected_reason,
       r.created_at,
       (SELECT string_agg(coalesce(l.document, '?') || ' x' || l.qty::text, ', ')
          FROM projects.order_inquiry_links l WHERE l.row_id = r.id) AS links
FROM public.sales_orders so
JOIN public.sales_order_lines sol ON sol.sales_order_id = so.id
JOIN projects.sales_order_lines psol ON psol.core_sales_order_line_id = sol.id
JOIN projects.order_inquiry_rows r ON r.so_line_id = psol.id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
WHERE so.so_number = 'SO429216'
ORDER BY sol.line_no, r.created_at, r.id;

-- The same for OI-2611-0048 alone (every row, live or not).
SELECT r.item_code, r.qty, r.verb, r.state, r.ack_state, r.redirected_to_pool,
       r.created_at, psol.core_sales_order_line_id
FROM projects.order_inquiries oi
JOIN projects.order_inquiry_rows r ON r.order_inquiry_id = oi.id
LEFT JOIN projects.sales_order_lines psol ON psol.id = r.so_line_id
WHERE oi.inquiry_no = 'OI-2611-0048'
ORDER BY r.item_code, r.created_at;
```

## Owner answers (5 Nov ~11:10 MYT)

Q1 (a) OI words; Q2 (a) the OI page's own PO / SPO chips with their click; Q3 (a) `ReserveText`;
Q4 Rejected pill + reason, click opens a lightbox, ONE shared component on SO and OI; Q5 (a) one
group per OI, one row, extra OIs behind "+N".

## Built

- BE `sales_order_service._line_inquiry_rows`: `order_inquiry_rows` per SO line, from
  `OrderInquiryWorklistService.list_rows(include_cancelled=True, row_ids=...)`, minus the
  narrative fields the cell never reads (review S2, `_SO_LINE_OI_ROW_DROPPED`).
  `order_inquiry` stays on the payload for API readers.
- FE `OrderInquiryLineStatusPill` (shared), `OrderInquiryLineDocuments.tsx` (chips moved out of
  the OI columns file), `OrderInquiryRejectedBadge` (pill + reason, Dialog), and
  `SoLineOrderInquiryCell`.

## Crew pass fixes (5 Nov)

1. Layout: the SO cell's PO and SPO chips painted over each other at 360px. One slot now
   (`LineDocumentsCompact`): the first chip truncates, every other PO/SPO chip sits behind
   one "+N".
2. A deep link (`?row=`) into an OI past 25 lines snapped back to page 1: TanStack's
   `autoResetPageIndex` fired on the next row-model recompute. Off in
   `OrderInquiryLinesTab`, with explicit resets on search, sort and filters and a clamp when
   lines shrink.
3. "Go to linked line" in the PO/SPO lightbox renders only when the loaded document holds
   the target line (it sat enabled or disabled with nothing to land on).

## Design note (pre-answer)

One shared FE function for "the status of a sales order line's OI rows" (the fold's
`foldInquiryLines` + the State cell's pill choice, lifted out of
`orderInquiryHeaderLinesColumns.tsx` into a shared component), used by both the OI Lines tab
and the SO Lines tab. The SO payload carries the line's rows in the OI row shape so the fold
runs unchanged; used and cancelled rows are dropped by the same `isLiveInquiryRow`.
