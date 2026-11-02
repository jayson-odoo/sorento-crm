# PLAN: Sample request two-stage tracking (PS-SAMPLE-TRACKING)

Status: Built, in review (PR #2098). Track: M lane (one additive migration), cloud.
UAC: `sample-tracking-02nov-acceptance-criteria.md`.

## Scope (owner rulings 2 Nov 2026)

- Stage 1 (Processing): when the sample team receives a request it starts processing and must
  answer whether the requested delivery date can be met, else propose a new date. The salesperson
  sees the answer.
- Stage 2 (Delivery): delivery comes from AutoCount, not a manual Delivered.
- Map today's statuses onto the two stages.
- Out of scope: 3-month return, auto invoice.

## Answers (crew + owner, 2 Nov)

- Q1 (a): no accept step. The date answer is one-way; the salesperson sees it.
- Q2 (a): keep Customer confirmed as the last Stage 1 step.
- Q3 / Q5: the owner ruled "The sample delivery document is the consignment", not a DO. Dev data
  backed it: 0 DO lines point at a consignment (all 48,165 sourced DO lines point at an SO), and 0
  of 5 sample requests carry a consignment number.
- Delivered date (crew b): the Overall Tracking `actual_delivery_date` of the `orders` row
  numbered like the CG, else the CG date. Data: 375 of 811 consignments (all since 29 Apr) have a
  tracking row, all of them dated, 0-46 days after the CG (median 2), never before.
- Q4 (a): a voided consignment undoes the delivery.
- Card changes: the Delivery date column sorts server-side; the stage filter is multi-select.

## Code facts (origin/main 46de2f6d)

- Statuses are the status-engine graph for `sample_request`
  (`project_seed_service.py:225-242`); moves = graph edges (`sample_request_service._edge_exists`).
- Submit already requires `delivery_date` (`validate_submit`), so every Submitted request has a date to
  answer.
- A CG is a `sales_orders` row with `doc_type='consignment'`, `so_number` = the CG DocNo,
  `status` `closed` when live and `cancelled` when voided or vanished (`autocount_consignment.py:143-164`). It
  stores no Ref or remark, so it carries no SR number: the link has to be explicit.
- The order tracking import (`order_service.import_excel_tracking`) upserts `orders` by the sheet's
  Doc. No. with no doc-type check, so a CG in Overall Tracking is an `orders` row numbered `CG-...`
  carrying `actual_delivery_date`.

## Design (as built)

### Stage 1

1. `stage_for(key)`: submitted/processing/customer_confirmed -> `processing`, delivered ->
   `delivery`, anything else -> null. The graph and its labels are unchanged.
2. `move(to=processing)` requires `date_feasible`. A No needs `proposed_delivery_date` (today or
   later, Malaysia time) and takes an optional `date_note` (255). A Yes clears any proposed date. The
   answer is stored with `date_answered_at/by`.
3. `PUT /sample-requests/{id}/date-answer` (process permission) changes the answer while the
   request is Processing or Customer confirmed; it returns 409 `SAMPLE_REQUEST_DATE_ANSWER_CLOSED` otherwise. Each change
   is a project activity row (`sample_request_date_answered`).
4. Rows and detail carry `stage`, `date_feasible` and `proposed_delivery_date`; detail adds `date_note`
   and `date_answered_at/by_name`. The list's `delivery_date` sort and its default order use
   coalesce(proposed, requested). `?stage=` is multi-select and replaces the open-status default.

### Stage 2

5. `GET /sample-requests/{id}/consignments?q=` (process): the company's non-cancelled consignments, by
   CG number or debtor, newest first, 20 rows.
6. `PUT /sample-requests/{id}/consignment {consignment_order_id}` (process; from Processing
   onwards). A live CG of the request's company is linked: `consignment_order_id` is stored,
   `consignment_no` is copied from it, and the request moves to Delivered, bypassing the graph edge
   because the CG is the fact. `delivered_at` = the delivery date, and `return_due` is computed from the loan.
   `null` unlinks and reverts. Anything else returns 422 `SAMPLE_REQUEST_CONSIGNMENT_INVALID`.
7. `consignment_delivery(db, cg)` is the one delivery source. It returns (tracking date, `tracking`)
   from the live, undeleted, non-cancelled `orders` row whose `order_number` equals the CG number
   (same company, case aside), else (CG date, `consignment`), else None for a voided CG.
8. Manual Delivered returns 409 `SAMPLE_REQUEST_DELIVERED_BY_CONSIGNMENT` while a CG is linked; with
   no CG (board-only, goods not through AutoCount) it stays.
9. Re-sync hooks:
   - `AutocountCancelIngestService._project_consignment` calls `sync_consignment(company, CG no)`.
     A voided CG moves the request back to Customer confirmed (Processing if it was never confirmed) and clears
     `delivered_at`/`return_due`; a restored CG delivers again.
   - `import_excel_tracking` calls `sync_tracked_orders(touched_orders)` before its commit, so a
     tracking date that lands after the link replaces the CG date.
10. `update_internal` keeps `consignment_no` as the linked CG's number while a CG is linked.

### FE

- Detail: Change to processing opens the date answer dialog (radio Yes/No, Proposed date, Note).
  The gear menu has Change date answer and Link consignment (async `SearchableSelect`). A Sample team
  line under Request Delivery Date shows the answer with a New date badge. Consignment No shows the linked CG and its date,
  with Voided in AutoCount when voided. Delivered names its source (Order Tracking / consignment
  date). Mark delivered is hidden while a CG is linked.
- List and project tab: the Delivery column shows the proposed date with a New date badge. A Stage filter
  (multi-select) is in Filters.
- Portal form: the Sample team answer line sits under Request Delivery Date (read-only).
- No Unlink button in the UI: it is a detach action (deferred-action rule); a wrong link is fixed by
  linking the right CG. The API still accepts `null`.

### Migration

`sst_0001_sample_tracking` (down `qcp_0001_cover_page_fields`): `date_feasible`,
`proposed_delivery_date`, `date_note`, `date_answered_at`, `date_answered_by` (FK users),
`consignment_order_id` (FK sales_orders, SET NULL) and an index. Additive and idempotent.

## Touch list (other PS lanes)

Sample request model, service, schema and FE are this lane's. Single-line hooks go into
`order_service.import_excel_tracking` and `autocount_cancel_ingest_service._project_consignment`
(no PS lane touches them). PS-PROPOSAL-QUOTATION may touch the sample request <-> proposal back-and-forth.

## Tests

- `tests/test_sample_request_tracking.py` (21): stages, date answer rules, list stage filter and sort.
- `tests/test_sample_request_consignment.py` (23): picker, link, refusals, manual Delivered guard,
  void/restore, unlink, tracking date source, late tracking sync.
- `tests/test_migration_sst_0001.py` (2).
- The SR-CORE, forms-chain and portal suites now send `date_feasible` on Start processing.
- FE: `lib/sample-request-tracking.test.ts` (6),
  `SampleRequestDetail.dateAnswer.test.tsx` (5), `SampleRequestDetail.consignment.test.tsx` (4).
