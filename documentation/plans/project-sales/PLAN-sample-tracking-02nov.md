# PLAN: Sample request two-stage tracking (PS-SAMPLE-TRACKING)

Status: Plan - behaviour card posted for answers (PR #2098). Track: M lane (one additive
migration), cloud.

## Scope (owner rulings 2 Nov 2026)

- Stage 1 (Processing): when the sample team receives a request it starts processing and must
  answer whether the requested delivery date can be met, else propose a new date. The salesperson
  sees the answer.
- Stage 2 (Delivery): delivery is the AutoCount DO. If a DO links to a consignment that links to the
  sample request, the request shows Delivered from that link; no manual Delivered when a DO exists.
- Map today's statuses onto the two stages.
- Out of scope: 3-month return, auto invoice.

## Code facts (origin/main 46de2f6d)

- Statuses are the status-engine graph for entity `sample_request`, seeded by
  `app/services/project_seed_service.py:225-242`: draft -> submitted -> processing ->
  customer_confirmed -> delivered, cancel from draft/submitted/processing. Legal moves =
  graph edges (`sample_request_service._edge_exists`, `:157`); permission by status KEY
  (`move`, `:562-612`).
- `move` to customer_confirmed / delivered requires a typed date; delivered sets `delivered_at`
  and `return_due = delivered_at + loan` (`sample_request_service.py:597-606`).
- The request already has a requested date (`delivery_date`, `models/sample_request.py:102`) and a
  coordinator-typed, free-text `consignment_no` (`:118`, written by `update_internal`,
  `sample_request_service.py:506-519`). Nothing validates it against AutoCount.
- `board_mounting` (`models/sample_request.py:114`) is a header flag, never a line; a request may
  be board-only with zero product lines (`validate_submit`, `sample_request_service.py:332`).
- An AutoCount Consignment (CG) is a `sales_orders` row with `doc_type='consignment'`,
  `so_number` = the CG DocNo (`autocount_consignment.consignment_payload`, `:101-145`).
- A DO is an `orders` row (`models/order.py:422`); each DO line keeps what AutoCount says it was
  transferred from: `from_doc_type`, `from_doc_no` (`models/order.py:594-595`). The DO ingest
  resolves `sales_order_line_id` only for `from_doc_type` NULL/'SO'
  (`autocount_doc_ingest_service.py:1169-1173`), so a CG-sourced DO line is stored with
  `from_doc_type='CG'`, `from_doc_no=<CG no>` and no resolved link. Header `ref_doc_no` resolves to
  an SO only (`:1134`).
- Caution: `autocount_consignment.py:12-16` + `PLAN-consign-delivered-fix-14oct.md` say a CG is
  itself a stock transfer to location CON ("goods already at the customer") and a CG line's
  TransferedQty is RETURNED qty, including returns suffixed 'CVT TO DO' (consigned goods converted
  to a sale). So a DO raised from a CG may be a conversion-to-sale, not the sample delivery. The
  real rows decide which (data request on the PR).

## Behaviour card

### Rules

1. **Two stages, shown as a stage line on the request.** Stage 1 "Processing" = Submitted,
   Processing, Customer confirmed. Stage 2 "Delivery" = Delivered. Draft and Cancelled sit outside.
   The stage is derived from the status KEY in one function; the graph and its labels are
   unchanged (no status rows added or removed).
2. **Start processing needs a date answer.** Submitted -> Processing requires the coordinator to
   answer "Can we meet <requested date>?": Yes, or No + a proposed date (must be on or after
   today) + an optional note (255). Stored on the request: `date_feasible`, `proposed_delivery_date`,
   `date_note`, `date_answered_at`, `date_answered_by`. The answer can be changed while the request
   is in Stage 1; each change is a project activity row (as moves are today).
3. **The salesperson sees it.** List: a "Delivery date" column shows the requested date, or the
   proposed date with a "New date" badge. Detail: under the header, "Requested 12 Nov 2026 - Sample
   team: can meet" or "Requested 12 Nov 2026 - Sample team proposes 19 Nov 2026: <note>". Portal
   requests show the same line. No accept step (Q1).
4. **Delivered comes from the DO.** A request is linked when its `consignment_no` equals a
   consignment's `so_number` (same company) and a live DO (not cancelled, not deleted, not vanished)
   has a line with `from_doc_type='CG'` and `from_doc_no` = that number. The link moves the request
   to Delivered with `delivered_at` = the DO date, `return_due` from the loan as today, and stores
   the DO (`delivery_order_id`, shown as the DO number with a link to the DO page).
5. **When the link is made.** Two writers, no polling: (a) the DO ingest, after it writes a DO with a
   CG-sourced line; (b) `update_internal`, when the coordinator sets or changes the consignment
   number and a DO already exists. One function `sample_request_service.apply_do_link`.
6. **No manual Delivered when a DO exists.** The Delivered move is refused (409,
   "Delivered is set by DO <no>") when a linked DO exists. With no linked DO the manual move stays
   (board-only requests, goods not via AutoCount, Q5).
7. **The consignment number is checked.** Saving a `consignment_no` that matches no consignment of
   the company is allowed but shows "No AutoCount consignment CG-... yet" (the CG may land later);
   the ingest links it when it arrives.

### Examples

Real rows not available in this sandbox (no dev DB). Data request posted on the PR for 5 masked
CG -> DO chains and 5 sample requests with a consignment number; the examples get filled from them.
Shapes the tests will use:

- SR-000101, requested 12 Nov, team answers Yes -> salesperson sees "can meet".
- SR-000102, requested 5 Nov, team answers No, proposes 14 Nov "stock from KL" -> list badge "New
  date 14 Nov".
- SR-000103 consignment CG-202611-010; DO-25110 line from CG CG-202611-010 dated 15 Nov lands ->
  Delivered 15 Nov, return due 15 Jan 2027 (2 months), DO-25110 shown.
- SR-000104 board-only, no CG -> coordinator moves Delivered by hand with a date.
- SR-000105 delivered by DO-25120, then DO-25120 is voided -> request goes back to Customer
  confirmed, delivered date and DO cleared (Q4).

### Edge cases

- Two DOs from one CG (partial deliveries): Delivered on the FIRST DO's date; the detail lists every
  DO from that CG.
- DO arrives before the request reaches Customer confirmed: the link still moves it to Delivered
  (the DO is the fact); the move skips the graph edge check, recorded as "Delivered by DO-...".
- Cancelled request: never linked.
- Same CG number typed on two requests: both link (no uniqueness; a warning on save).
- Requested date empty: the date question is skipped, Start processing works as today.

### Questions (each with a recommendation)

1. Must the salesperson accept a proposed new date? (a) No: shown + notified, they cancel or
   comment if it does not work; (b) Yes: an Accept / Reject step before the team continues.
   **Recommend (a)**: fewest moving parts, the cancel and comment paths exist already.
2. Customer confirmed: (a) keep it as the last Stage 1 step; (b) retire it (Processing -> Delivered).
   **Recommend (a)**: no data move, admins already edit the graph.
3. Delivered date: (a) the DO date; (b) the DO's tracked delivery date (Order Tracking), pending until
   tracked. **Recommend (a)**: one rule, tracking often lands days later or never on older DOs.
4. DO voided after linking: (a) revert to Customer confirmed and clear the DO; (b) keep Delivered.
   **Recommend (a)**: the DO is the fact; a voided DO delivered nothing.
5. Is CG -> DO really the sample delivery in AutoCount, or is it the 'CVT TO DO' sale conversion?
   (a) delivery (link as above); (b) conversion: then the sample DO links some other way (DO Ref /
   remark holding the SR or CG number). **Recommend (a) pending the masked rows**; the matcher is one
   function, so switching to (b) changes only it.

## Touch list (other PS lanes)

`sample_request.py` model + service + schema + `sample-requests` FE are this lane's; PS-PROPOSAL-
QUOTATION may touch sample request <-> proposal back-and-forth (will merge main often).
`autocount_doc_ingest_service.py` gets one post-write call (no PS lane touches it).
One additive migration on `projects.sample_requests`.
