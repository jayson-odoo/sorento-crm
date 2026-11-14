# UAC: SPARE-PART-OR-B (slice 2 of #2381)

Crew 14 Nov 15:50: Q1 (a), Q3 (a), Q5 (a) decided. Q2 assumed (a) for R5. Q4 open: no R4 code beyond "approved qty only, no was" until answered.

## R1 Approver edit: History icon beside Qty, no "was"
- U1.1 On a spare part request line (OR page and OI page) no text matching /^was /i renders in the Qty or Unit price cell, in any state, for any viewer (WasMark gone from spare part lines).
- U1.2 Every spare part line renders exactly ONE History button (aria-label "History"), inside the Qty cell, after the value/input. The State cell of a spare part line has no History button.
- U1.3 The button carries `data-changed="true"` when the line changed: qty differs from submitted qty, OR unit price differs from submitted unit price, OR photo_changes added+removed > 0. Otherwise `data-changed="false"` (muted styling).
- U1.4 Clicking it calls `onLineHistoryClick(line)` (the existing `OrderInquiryLineHistoryDialog`), and does not toggle row selection / expansion.
- U1.5 The Qty cell stays one line: the input/value and the icon sit in one `flex items-center` row (no flex-col).
- U1.6 Sales-order inquiry lines are unchanged (their History button stays where it is).

## R2 OI number at final approval (same record)
- U2.1 Migration adds `projects.order_inquiries.oi_no varchar(20) NULL` and a unique index on (company_id, oi_no) where oi_no is not null. Additive only; single alembic head; revision id <= 32 chars.
- U2.2 Backfill: every `spare_part_request` header whose state is not draft / pending_approval / rejected and has no oi_no gets one, in raised_at order (then inquiry_no), numbered `OI-YYMM-NNNN` by the month of its raised_at (Asia/Kuala_Lumpur), continuing after the highest OI- number already issued that month (inquiry_no OR oi_no) for that company. Idempotent (a second run changes nothing).
- U2.3 Final approval (`spare_part_request_service.approve`, the branch that sets state raised) sets `oi_no` once from the OI- series. A non-final approval (another level open) sets nothing.
- U2.4 The OI- series counts both columns: a sales-order OI created after a spare part approval in the same month takes the next number after the spare part's oi_no, and vice versa (`next_inquiry_no` considers inquiry_no and oi_no). No collision ever.
- U2.5 Revise keeps oi_no; the re-approval does not mint a second number.
- U2.6 Draft / pending / rejected requests have oi_no null; the API returns `oi_no: null`.
- U2.7 `oi_no` is returned by: the spare part request detail (`spare_part_request_service.detail`), the spare part request list rows, the OI header list rows and detail (`OrderInquiryHeaderOut`, `OrderInquiryDetail`), and each OI worklist / lines row (`OrderInquiryWorklistRow.oi_no`, the row's header's oi_no). Asserted in tests (response_model drops undeclared fields).
- U2.8 OI header list search matches oi_no as well as inquiry_no.

## R3 One shared link cell, both directions
- U3.1 `SoLineOrderInquiryCell`'s entry view is lifted to ONE shared component `app/(protected)/project-sales/_shared/components/OrderInquiryLinkCell.tsx` (export `OrderInquiryLinkCell`, `orderInquiryLinkEntries`); `SoLineOrderInquiryCell` becomes a thin caller (or is replaced) and SO line rendering is unchanged (existing SO tests still pass).
- U3.2 OR page Lines tab (spare part columns, viewed from the OR record): an "OI" column after State. For a line whose header has oi_no and whose row is not cancelled: link text = oi_no, href `/project-sales/order-inquiries/<inquiry id>?row=<row id>`. Otherwise "-". Same component as U3.1.
- U3.3 OI page Lines tab of a spare part inquiry: first data column "Order request" showing the OR number (inquiry_no) as a link to `/procurement-management/spare-part-requests/<inquiry id>?line=<row id>`; mirror of the SO No. link (same Link styling, stopPropagation).
- U3.4 Purchasing-facing labels: the OI page header title and the OI header list No. cell show `oi_no` when set, else inquiry_no. The OR page header title stays inquiry_no (OR-).
- U3.5 Both new columns: explicit size, truncate + title, hideable in Columns, one line.

## R4 (partial until Q4) OI page shows approved qty only
- U4.1 On the OI page (not the OR page) a spare part line shows no submitted qty / submitted price and no "was" (covered by U1.1).
- U4.2 On the OI page the History button's data-changed is true only when the line has a qty or price change AFTER the first raise (see U5.2), not for pre-approval changes. HOLD until Q4: any ack_state change.

## R5 History meaning (Q2 assumed (a))
- U5.1 `GET /order-inquiry-headers/{id}/history` unchanged by default (whole life): the OR page History tab and line lightbox show created, edited, submitted, line changed (old -> new), approved, rejected, revised, raised, purchasing events.
- U5.2 `GET /order-inquiry-headers/{id}/history?scope=inquiry`: for a spare part request, only events at or after its FIRST raise (earliest `order_inquiry_raises.raised_at` for it): Raised, purchasing presses / links / rejections, and any SPR_LINE_CHANGED / SPR_EDITED / SPR_REVISED / SPR_APPROVED after it. Nothing before. For a sales-order inquiry, scope=inquiry returns the same as the default.
- U5.3 A spare part request never raised + scope=inquiry -> empty list (200).
- U5.4 FE: `OrderInquiryHistory` takes `scope?: 'record' | 'inquiry'`; the OI page (OrderInquiryDetail) and its line lightbox pass 'inquiry' for spare part inquiries; the OR page passes nothing (record).
- U5.5 Example E2: approver 10 -> 8, approve, revise, requester 8 -> 20, approve. scope=inquiry shows the 8 -> 20 change and both raises but not 10 -> 8; default shows all.
