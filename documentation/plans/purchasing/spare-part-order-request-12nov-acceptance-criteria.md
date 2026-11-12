# UAC: Stock order request (spare parts), routed to purchasing as an Order Inquiry type

Status: DRAFT, written against card v3's recommendations (PR #2381): ONE record, the request is an Order Inquiry of type spare_part_request, opened on the existing OI page. Lines tagged
[Qn] change if the owner answers question n differently. Not a build contract until answers land.

## Request (requester)
- R1 A user with `procurement.stock_order_requests.create` can create a request with currency (required, one per request), needed-by date, an optional default location, reason, and one or more product lines.
- R1a (owner, mock v1 note) Location is per line, like AutoCount: each line has its own location (required on Submit), a new line starts with the header default when one is set, and changing the default never rewrites existing lines. The picker lists locations from `location_stock_service.location_stock_for_product` with stock shown as information only (never caps qty). The OI row carries it in its existing `stock_location`.
- R1b (owner, mock note 8, 12 Nov 20:00, supersedes note 4) One type only: Spare part request. No Consignment type; no customer field.
- R1c (owner, mock notes 3 and 7) The request opens on the existing Order Inquiry page: same header card and tabs (Lines, General, Related PO, Related SPO, History); request fields as Request / Approval cards in the General tab layout; lines in the Lines tab with Unit price and Total.
- R1d (owner, mock note 5) Each line expands to the existing OI stock table (`OrderInquiryStockGrid`), on the form and on the OI page; information only.
- R1e (owner, mock note 6) Line attachments use `SoLineAttachmentsButton` (paperclip, count, lightbox) on the form and on the OI page.
- R2 [Q3] Each line picks a catalogue product (searchable by code and name); description fills from the product; quantity > 0 and unit price >= 0 are required on Submit, not while typing.
- R3 Line total = qty x unit price, worked out server-side and shown; the request total is the sum, in the request currency.
- R4 Photos attach per line through the same attachment service and lightbox as fulfilment planning (R1e).
- R5 Save as draft keeps the request editable; Submit moves it to Pending approval level 1 and stamps submitted_at; the number reads `SOR-YYMM-NNNN`.
- R6 A requester sees their own requests; the list is the standard DataGrid (search, multi-select filters, server sort, columns, Create).

## Approval [Q2]
- A1 Approval levels are `form_sla_configs` rows for `stock_order_request`, chained by `next_config_id`; with no row configured, Submit is refused with a plain message telling the admin to set the approval stage.
- A2 Only an active member of the current stage's team, or an admin, may Approve or Reject; the requester never may, even if a team member. Anyone else gets 403.
- A3 (owner, mock note 9) While Pending approval the approver may change each line's quantity (including 0), unit price, and photos (add / delete through the same attachment lightbox). The requester's submitted qty and unit price are kept on the line and shown as "was ..." next to a changed value, on the approval screen and on purchasing's view. Every change is a History row (old -> new, by whom). The approver cannot add or remove lines; qty 0 drops a line from what purchasing receives. [Q5]
- A4 Approve with every line at 0 is refused (422, message next to the action).
- A5 Reject requires a reason; the request returns to the requester as Rejected, editable; resubmit restarts at level 1.
- A6 Approve on a non-final level moves to the next level and notifies that team; on the final level the request becomes Approved and locked.

## Purchasing hand-off [Q1]
- P1 [Q1] Final approval moves the request's own Order Inquiry from pending_approval to raised (no second record) and is the moment purchasing first sees it; before that, purchasing's list and notifications exclude it. Formerly: final approval raises exactly one Order Inquiry with `inquiry_type` = `spare_part_request`, no sales order, in the same OI number series, in the same transaction as the approval.
- P2 One OI row per approved line with qty > 0 (verb ORDER, ack awaiting), carrying product code, description, qty, unit price, currency, and a link to the line's photos.
- P3 Purchasing users (`purchasing%` roles) get the existing order-inquiry notification; no notification goes out before final approval.
- P4 The Order Inquiries list shows a Type column and a Type multi-select filter; SO-driven inquiries read "Sales order", the new ones "Spare part request"; the SO cell for this type reads "-".
- P5 OI detail for this type shows requester, approver, approved date, currency, a link to the request, and unit price / total / photo columns; acknowledge and per-row reject work as for SO-driven inquiries.
- P6 Existing SO-driven inquiries are untouched: the migration backfills `inquiry_type = 'sales_order'`, and a CHECK keeps `project_sales_order_id` required for that type.

## Change after approval [Q4]
- V1 While no OI row is acknowledged, the requester may Revise: the inquiry returns to Draft (leaves purchasing's list) and approval restarts on Submit.
- V2 Once any row is acknowledged, Revise is not offered and the server refuses it.

## History, permissions, assistant
- H1 Every tracked action (submit, approve, reject, qty change, OI raised, revise) shows on the request's History tab (shared AuditTrail).
- H2 New slugs registered in the permission registry: `procurement.stock_order_requests.view`, `.create`, `.approve`.
- H3 The assistant can list stock order requests and read one (registry entry + two eval prompts), or the PR says why not.
