import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { LinkHorizonRequest } from '../lib/linkHorizon';
import type {
  AcknowledgeResult,
  AutoPlaceRequest,
  AutoPlaceResult,
  OrderInquiryDetail,
  OrderInquiryListEnvelope,
  OrderInquiryListParams,
  OrderInquiryPoAllocation,
  OrderInquiryBulkRejectResult,
  OrderInquiryPoCandidate,
  OrderInquiryPoDetail,
  OrderInquiryRow,
  OrderInquirySpoDetail,
  OrderInquirySummary,
  OrderInquiryWorklistEnvelope,
  OrderInquiryWorklistParams,
  OrderInquiryWorklistRow,
  OrderInquiryWorklistSummary,
  UnplaceAllPreview,
  UnplaceAllRequest,
  UnplaceAllResult,
  UploadJobScope,
} from '../types/orderInquiry.types';

const BASE = '/api/v1/project-sales';

/**
 * Order inquiry rows (P10, contract section 7).
 *
 * Rows are never created from the browser. They are DERIVED when CS confirms a Project SO
 * in Fulfilment Planning (the Buy residual of the confirmed revision, Stage 1C) or when an
 * amendment publishes, which are the only moments the instruction is true. What this
 * service does is read them, export them and record what purchasing did about them.
 */

function normaliseEnvelope(body: unknown, fallbackLimit: number): OrderInquiryListEnvelope {
  const raw = (body ?? {}) as {
    data?: OrderInquiryRow[];
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(raw.data) ? raw.data : [];
  return {
    data: rows,
    total: raw.pagination?.total ?? rows.length,
    page: raw.pagination?.page ?? 1,
    limit: raw.pagination?.limit ?? fallbackLimit,
  };
}

function searchParams(params: OrderInquiryListParams, limit: number) {
  return buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : [],
      searchQuery: params.query ?? '',
    },
    {
      verb: params.verb,
      state: params.state,
      sales_order_id: params.sales_order_id,
    },
  );
}

export async function listOrderInquiryRows(
  projectId: string,
  params: OrderInquiryListParams = {},
): Promise<OrderInquiryListEnvelope> {
  const limit = params.limit ?? 25;
  const search = searchParams(params, limit);
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/order-inquiry-rows?${search.toString()}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the order inquiry'));
  return normaliseEnvelope(await response.json(), limit);
}

export async function getOrderInquirySummary(
  projectId: string,
): Promise<OrderInquirySummary> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/order-inquiry-summary`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the order inquiry totals'));
  return response.json();
}

/** What purchasing was told when one sales order published. */
export async function getSalesOrderInquiry(psoId: string): Promise<OrderInquiryDetail> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/order-inquiry`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this order inquiry'));
  return response.json();
}

/** Purchasing records what happened to one row or to a selection of them (AC-I7). */
export async function markOrderInquiryRows(
  rowIds: string[],
  state: string,
): Promise<OrderInquiryRow[]> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/mark`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row_ids: rowIds, state }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to update those rows'));
  return response.json();
}

/* -------------------------------------------------- Link PO / Link SPO (section 3.I)
 *
 * API CONTRACT (PLAN-scm-cs-planning-uat.md section 3.I, AC-I1 to AC-I10). The ROUTE
 * PATHS are unchanged on purpose - the plan renames the verb, not the URLs - so
 * `place-on-po` is the link endpoint and `unplace` is the unlink one.
 *
 *   GET  {BASE}/order-inquiry-rows/{rowId}/po-candidates
 *        -> OrderInquiryPoCandidate[], in the walk's own order: the cited document first,
 *        then SPO allocations before PO lines on an ORDER BACK row, then location tier
 *        (Q5), then the PO's issue date, then the line's expected date, then the document
 *        number (Q7). Every candidate carries BOTH dates and its tier; location never
 *        filters a candidate out. `default_take` is the cascade's own preview of what it
 *        would take off that line. 409 when the row is not linkable.
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/place-on-po  { po_line_id }
 *        -> OrderInquiryRowOut. One PO line, the single-target shape.
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/place-on-po
 *        { allocations: [{po_line_id | spo_allocation_id, qty}] }
 *        -> OrderInquiryRowOut - the SAME row, with one link per allocation. The row is
 *        never split any more (AC-I6): it keeps its full quantity and reads linked or
 *        partly linked. 409 `order_inquiry_over_allocated` when the allocations total
 *        more than the row's own quantity; 409 `order_inquiry_po_line_short` naming the
 *        line that cannot cover what was asked of it; 409
 *        `order_inquiry_spo_not_linkable` when a row whose verb cannot be linked at all
 *        names a document (every linkable verb may name either book since 27 Aug).
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/unplace  { link_id? }
 *        -> OrderInquiryRowOut. With a `link_id` that ONE link goes; without one every
 *        link the row holds goes. The row's state is re-derived either way. 409 when the
 *        row holds no links at all.
 *
 *   POST {BASE}/order-inquiries/auto-place  { product_ids? }
 *        -> AutoPlaceResult { placed_rows, allocations, products_touched }. Runs the
 *        cascade now, over every raised or partly linked row of the named products (or of
 *        every product carrying one, when `product_ids` is omitted). Idempotent - a
 *        second call links nothing further.
 *
 *   GET  {BASE}/order-inquiries/unplace-all-preview  { query?, delivery_month?,
 *        raised_date?, project_id?, supplier_id?, raised_by? }
 *        -> UnplaceAllPreview { count, product_code?, product_name? }. The confirm
 *        dialog's own numbers, resolved server-side against the SAME filters
 *        `unplace-all` itself reads - never off whatever page of the worklist happens to
 *        be loaded. `product_code`/`product_name` are set only when every matching row
 *        resolves to the same product.
 *
 *   POST {BASE}/order-inquiries/unplace-all  { ...the same filters }
 *        -> UnplaceAllResult { unplaced }. Every LINKED or partly linked row matching the
 *        CURRENT worklist scope loses its links. No filter at all means every linked row
 *        in the company. Never `product_ids`: the worklist paginates server-side, so a
 *        client-derived product list would miss rows behind page 1.
 *
 * Permission is the same as `mark`: `projects.order_inquiry.action`.
 */

export async function getOrderInquiryPoCandidates(
  rowId: string,
): Promise<OrderInquiryPoCandidate[]> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/po-candidates`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load candidate lines'));
  return response.json();
}

/** Link a row to ONE outstanding PO line - the single-target shape. */
export async function placeOrderInquiryRowOnPo(
  rowId: string,
  poLineId: string,
): Promise<OrderInquiryRow> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/place-on-po`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ po_line_id: poLineId }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to link this row to a document'));
  return response.json();
}

/**
 * Link a row across one or more document lines - PO lines, or SPO allocations on an
 * ORDER BACK row - in one call. The row keeps its full quantity and gains one link per
 * allocation, so the response is that same row.
 */
export async function placeOrderInquiryRowOnPoAllocations(
  rowId: string,
  allocations: OrderInquiryPoAllocation[],
): Promise<OrderInquiryRow> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/place-on-po`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ allocations }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to link this row to a document'));
  return response.json();
}

/** Unlink: one link when `linkId` names it, every link the row holds when it does not. */
export async function unplaceOrderInquiryRow(
  rowId: string,
  linkId?: string,
): Promise<OrderInquiryRow> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/unplace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(linkId ? { link_id: linkId } : {}),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to unlink this row'));
  return response.json();
}

/**
 * Run the cascade now - the worklist's "Auto-link". Every raised or partly linked row of
 * the named products, or of every product carrying one when `product_ids` is omitted,
 * linked to its own open document lines in the walk's order. Idempotent: a second call
 * links nothing further.
 */
export async function autoPlaceOrderInquiryRows(
  params: AutoPlaceRequest = {},
): Promise<AutoPlaceResult> {
  const response = await apiFetch(`${BASE}/order-inquiries/auto-place`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to run the auto-link pass'));
  return response.json();
}

/**
 * Purchasing takes these instructions on (AC-H2), one row or a batch.
 *
 * One press does two things because they are one decision: the rows become purchasing's
 * work, and the cascade runs for exactly them, so whatever open document can cover them
 * is linked at that moment. Nothing links before this.
 *
 * `horizon` is how far out the linking half reaches (AC-LH1): every ticked row is taken
 * on, and one due after that date is left Not linked and reported on `after_horizon`. It
 * is `linkHorizonRequest`'s own fragment - a date, an explicit `link_horizon: 'none'`, or
 * nothing at all, which the server reads as the reorder plan's own (S1).
 */
export async function acknowledgeOrderInquiryRows(
  rowIds: string[],
  horizon?: LinkHorizonRequest,
): Promise<AcknowledgeResult> {
  const response = await apiFetch(`${BASE}/order-inquiries/acknowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row_ids: rowIds, ...(horizon ?? {}) }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to acknowledge those rows'));
  return response.json();
}

/**
 * Purchasing refuses one row, with a reason (AC-H5). The row leaves netting and its
 * sales-order line goes back to the board undecided carrying the refusal.
 */
export async function rejectOrderInquiryRow(
  rowId: string,
  reason: string,
): Promise<OrderInquiryRow> {
  const response = await apiFetch(`${BASE}/order-inquiries/${rowId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to reject this row'));
  return response.json();
}

/**
 * Purchasing refuses a BATCH with ONE reason (plan section 5.6, item 15). Reject is a
 * bulk action now that the row actions column is gone, and asking for the reason once
 * per row would make refusing twenty rows twenty dialogs.
 *
 * ONE call, and the server takes it all or nothing: a press that half happened leaves the
 * buyer to work out which half from a screen that has already moved on.
 */
export async function rejectOrderInquiryRows(
  rowIds: string[],
  reason: string,
): Promise<OrderInquiryBulkRejectResult> {
  const response = await apiFetch(`${BASE}/order-inquiries/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row_ids: rowIds, reason }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to reject those rows'));
  return response.json();
}

/**
 * What the book this page uploaded has written (AC-H13), once the worker is done with it.
 * The two next steps read it: the products to link against, the documents to go and look
 * at. Asked for by the job id the upload dialog handed back.
 */
export async function getOrderInquiryUploadJob(jobId: string): Promise<UploadJobScope> {
  const response = await apiFetch(`${BASE}/order-inquiries/upload-jobs/${jobId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to read that upload'));
  return response.json();
}

/**
 * Run the cascade over ACKNOWLEDGED rows now (AC-H13) - what the buyer presses once an
 * uploaded book has landed. `product_ids` narrows it to what the upload touched.
 */
export async function linkNowOrderInquiryRows(
  params: AutoPlaceRequest = {},
): Promise<AutoPlaceResult> {
  const response = await apiFetch(`${BASE}/order-inquiries/link-now`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to link those rows'));
  return response.json();
}

/** The same fields, however they are used - a query string for the preview GET, a
 * JSON body for the commit POST. No page/sort/limit: neither endpoint paginates. */
function unplaceAllSearchParams(filters: UnplaceAllRequest): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.query) params.set('query', filters.query);
  if (filters.delivery_month) params.set('delivery_month', filters.delivery_month);
  if (filters.raised_date) params.set('raised_date', filters.raised_date);
  if (filters.project_id) params.set('project_id', filters.project_id);
  if (filters.supplier_id) params.set('supplier_id', filters.supplier_id);
  if (filters.raised_by) params.set('raised_by', filters.raised_by);
  return params;
}

/**
 * The confirm dialog's own count, for the CURRENT worklist scope - resolved server-side
 * against the same filters `unplaceAllOrderInquiryRows` itself takes, so the number a
 * person confirms and the rows the commit actually touches can never disagree.
 */
export async function getUnplaceAllPreview(
  filters: UnplaceAllRequest = {},
): Promise<UnplaceAllPreview> {
  const qs = unplaceAllSearchParams(filters).toString();
  const response = await apiFetch(
    `${BASE}/order-inquiries/unplace-all-preview${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the unlink count'));
  return response.json();
}

/**
 * "Unlink all" for the CURRENT worklist scope: every linked or partly linked row matching
 * the SAME filters the worklist list reads loses its links in one call, so Auto-link can
 * re-deal them. No filter at all means every linked row in the company.
 */
export async function unplaceAllOrderInquiryRows(
  params: UnplaceAllRequest = {},
): Promise<UnplaceAllResult> {
  const response = await apiFetch(`${BASE}/order-inquiries/unplace-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to unlink those rows'));
  return response.json();
}

/* ------------------------------------------------ the cross-project worklist
 *
 * API CONTRACT. Written in Phase 1 against a fixture, before any backend existed, and
 * this is what the routes were then built to satisfy.
 *
 *   GET  {BASE}/order-inquiries
 *        query, delivery_month=YYYY-MM, raised_date=YYYY-MM-DD, state, project_id,
 *        supplier_id, raised_by, linked, kind, page, limit, sort, dir
 *        S1 (PLAN-scm-oi-worklist-excel-parity.md, R-K) adds: location (warehouse code,
 *        equality), agent (sales agent id, equality), so_month=YYYY-MM (on the SO date),
 *        po_number / spo_number (prefix, case-insensitive - `po_number` hits a PO link's
 *        `document` AND an SPO link's `source_po_number`; `spo_number` hits an SPO
 *        link's own `document` - a REAL link only, never a derived SPO entry, which is
 *        computed for display and matches no row of `order_inquiry_links` to filter on).
 *        kind=spo|po|buy is the cards' own filter (AC-I11), now the R-F STAGES (S5): buy
 *        is unlinked, po is on a purchase order line but not yet on a shipment
 *        (`min(qty - incoming, po_linked - derived_spo_cover)`), spo is incoming - on an
 *        SPO allocation, own link or derived via its linked PO line. A row linked 5 of 8
 *        to a purchase order answers to po AND to buy alike, and a cancelled row to
 *        neither.
 *        query also matches the name and the email prefix of the CS who raised it, and
 *        (S1) a link document, an SPO link's `source_po_number`, and the sales agent's
 *        code/name.
 *        -> { data: OrderInquiryWorklistRow[], pagination: {total,page,limit}, empty }
 *        sort is a CLOSED set - so_date, so_number, item_code, product_name, qty,
 *        delivery_date, project_customer, supplier, po_number, state, raised_at,
 *        raised_by_name - and an unknown value is a 422, never a silent fall back to
 *        the default.
 *
 *   GET  {BASE}/order-inquiries/summary
 *        the same filters, no paging
 *        -> { total_rows, total_qty, by_state,
 *             by_month: [{month,label,rows,qty}], suppliers: [], projects: [],
 *             raised_by: [], locations: [], agents: [], kinds: {spo,po,buy} }
 *        `locations`/`agents` (S1) are the Location/Agent filters' own lists, same shape
 *        as `suppliers` (`[{id,label,rows}]`), each computed with its own filter dropped.
 *        `kinds` is the three cards above both views, in R-F's stage order (Buy,
 *        Purchased, Incoming) - quantity still unlinked, on a purchase order line, on an
 *        SPO allocation (own or derived). The TOTALS honour `kind` like every other
 *        filter, because they describe what is on screen; the `kinds` facet itself drops
 *        it, so pressing one card leaves the other two readable.
 *        PLAN-scm-supplied-with-companions.md (owner, plan review): a `bundled_qty` is
 *        in NONE of the three cards - it rides inside another line's own supply, so it
 *        is not owed anywhere. Every card subtracts `bundled_qty` from what it would
 *        otherwise count; `kind=buy` follows the same rule, so a fully-bundled row (its
 *        whole qty rides along) never appears under `kind=buy` and a partly-bundled row
 *        does, for its ala carte remainder only.
 *        `raised_by` lists only the people who have actually raised one of the rows in
 *        view, id + name, which is what the "Raised by" filter offers.
 *        The totals honour every filter. The AXES each ignore their own filter on
 *        purpose: they are the screen's controls, and a control that empties itself the
 *        moment it is used cannot be used a second time.
 *
 *   GET  {BASE}/order-inquiries/export
 *        the same filters, no paging -> xlsx, one sheet per delivery month.
 *
 * PLAN-scm-supplied-with-companions.md, S5: every row carries two fields, derived
 * server-side by `derive_bundles`, never typed -
 *   bundled_qty  : string, same convention as every other quantity here
 *   bundled_with : { row_id, item_code, item_codes, anchor_headline } | null
 *                  `item_codes` names every item the rule requires (length 1 or, for a
 *                  pair rule, 2+); `row_id` addresses the ANCHOR row (the rule's first
 *                  matching item) so the info icon can open ITS lightbox for a row that
 *                  has none of its own. `anchor_headline` (review round 1 item 8) is the
 *                  anchor's OWN coverage - "1 of 1" - resolved server-side, once per
 *                  page, in `OrderInquiryWorklistService._anchor_headline_by_id`: the
 *                  cell renders this directly rather than scanning its own loaded rows
 *                  for a match, which is only ever right when the anchor happens to be
 *                  on the SAME page as its companion. Null when the anchor has no links
 *                  of its own yet - the cell falls back to a plain dash (S5).
 * `response_model` drops a field nobody declares, so both are asserted directly against
 * a fixture row in `test_order_inquiry_bundles.py` (`test_d7`, `test_d7c`).
 *
 * PLAN-scm-oi-worklist-excel-parity.md, S5 (R-D, R-E): every PO link gains an SPO
 * allocation matching `from_po_number = po_number AND product_id`, open per
 * `spo_supply.open_incoming_clauses`, emitted as a SYNTHETIC entry on `links[]`:
 * `{ kind: 'spo', derived: true, document, qty, location, expected_date, id }` - never
 * written, so `committed_v` and every demand read stay on real links only. The mirror:
 * an SPO link whose `source_po_number` is shown as "the PO" carries `derived_po: true`.
 * Both flags are absent/false on a real link. The error code for an SPO placement
 * refused by verb is `order_inquiry_spo_not_linkable` (renamed from
 * `order_inquiry_spo_not_order_back` - every linkable verb, not only ORDER BACK, per the
 * 27 Aug widening).
 *
 * `PLAN-oi-replan-received-links.md`, S1/S3 (Phase 1, mocked - no backend yet):
 *
 *   - Every link in `links[]` gains two fields, both read off the document line
 *     `links_for_rows` already joins (`PurchaseOrderLine.qty_received` /
 *     `SPOAllocation.quantity_received`, plus `open_incoming_clauses()` for an SPO):
 *       received      : boolean  - the document is FULLY received (PO: `qty_received >=
 *                        qty_ordered` or `line_status = 'closed'`; SPO: fails
 *                        `open_incoming_clauses()`). Absent/false on an open document.
 *       received_qty  : string | null - how much of THIS link's line has been received,
 *                        stated even on a link that is only PARTLY received.
 *     The PO/SPO chip (`DocumentsCell`) reads the first entry's `received` for a muted
 *     `received` mark beside the number, and its `title` becomes `<document> - received
 *     <received_qty> of <qty>`; the backing-documents dialog prints `received
 *     <received_qty>` beside every received link's own location/quantity line.
 *
 *   - Every row in `OrderInquiryWorklistRow` gains:
 *       redirected_to_pool : boolean - true once a replan met a row whose only coverage
 *                        was a fully received document and could not carry it forward
 *                        (S2, backend). The row keeps its old `qty`/`delivery_date`/
 *                        `links` as history; a fresh, unlinked ORDER row carries the new
 *                        need instead. The Qty cell marks a redirected row with a muted
 *                        `redirected` mark, and the Buy / Purchased / Incoming card
 *                        totals (`summary.kinds`) ignore it entirely - it is not owed
 *                        anywhere any more, whatever its `state` or `links` still say.
 *     Absent or false on every row today - 0 rows carry it on the 15 Sep prod copy; S2 is
 *     its first writer.
 *
 * Rows come from EVERY project and from every adopted AutoCount order, which belongs to
 * no project at all. Permission is `projects.projects.view`, the same read the module
 * already grants.
 *
 * The Schedule matrix (List | Schedule) is its own endpoint now (S3,
 * `orderInquiryMatrixService.ts`) - `GET {BASE}/order-inquiries/matrix`, documented
 * there. It replaced an unpaged list fetch grouped client-side, which capped at
 * `MATRIX_FETCH_LIMIT` (1,000) rows a delivery-filtered worklist has already exceeded.
 */

/** Exported so `orderInquiryMatrixService.ts` builds the SAME filter set the list and
 * summary do - one function, so a filter added here never drifts out of step with the
 * matrix's own request. */
export function worklistParams(params: OrderInquiryWorklistParams, limit: number) {
  return buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : [],
      searchQuery: params.query ?? '',
    },
    {
      delivery_month: params.delivery_month,
      raised_date: params.raised_date,
      state: params.state,
      project_id: params.project_id,
      supplier_id: params.supplier_id,
      raised_by: params.raised_by,
      linked: params.linked,
      kind: params.kind,
      // `to_confirm` travels as itself: the server reads it as awaiting OR changed on the
      // list, the summary facet and the export alike (R3), so the page's default filter is
      // one value rather than two the client would have to union.
      ack: params.ack,
      // S1, R-K.
      location: params.location,
      agent: params.agent,
      so_month: params.so_month,
      po_number: params.po_number,
      spo_number: params.spo_number,
      delivery_from: params.delivery_from,
      delivery_to: params.delivery_to,
      // S3: a Schedule cell's own drilldown. The pair is sent as the pair - the server
      // ignores either half alone.
      axis: params.axis,
      axis_key: params.axis_key,
    },
  );
}

/** Everything purchasing has been told to buy, across every project and adopted order. */
export async function listOrderInquiryWorklist(
  params: OrderInquiryWorklistParams = {},
): Promise<OrderInquiryWorklistEnvelope> {
  const limit = params.limit ?? 25;
  const search = worklistParams(params, limit);
  const response = await apiFetch(`${BASE}/order-inquiries?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the order inquiry'));
  const body = (await response.json()) as {
    data?: OrderInquiryWorklistRow[];
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(body.data) ? body.data : [];
  return {
    data: rows,
    total: body.pagination?.total ?? rows.length,
    page: body.pagination?.page ?? 1,
    limit: body.pagination?.limit ?? limit,
  };
}

/** The month strip and the state counts behind the list. */
export async function getOrderInquiryWorklistSummary(
  params: OrderInquiryWorklistParams = {},
): Promise<OrderInquiryWorklistSummary> {
  const search = worklistParams(params, 25);
  search.delete('page');
  search.delete('limit');
  search.delete('sort');
  search.delete('dir');
  const qs = search.toString();
  const response = await apiFetch(
    `${BASE}/order-inquiries/summary${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to load the order inquiry totals'),
    );
  return response.json();
}

/**
 * The whole filtered set as the workbook purchasing already reads: one sheet per
 * delivery month, their headings, their column order.
 *
 * Paging is dropped for the same reason the per-project export drops it: an export of
 * page two of a filtered set is a file nobody can use.
 */
export async function downloadOrderInquiryWorklistXlsx(
  params: OrderInquiryWorklistParams = {},
): Promise<Blob> {
  const search = worklistParams(params, 25);
  search.delete('page');
  search.delete('limit');
  search.delete('sort');
  search.delete('dir');
  const qs = search.toString();
  const response = await apiFetch(`${BASE}/order-inquiries/export${qs ? `?${qs}` : ''}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to export the order inquiry'));
  return response.blob();
}

/**
 * The "PO no" cell's popup: that purchase order's own header and every one of its
 * lines, not only the one this row happened to be tagged to. Gated the same as the
 * worklist's own read (`projects.projects.view`) - never the SCM purchase-orders route,
 * which purchasing on this worklist holds no grant for.
 */
export async function getOrderInquiryPoDetail(poId: string): Promise<OrderInquiryPoDetail> {
  const response = await apiFetch(`${BASE}/order-inquiries/po/${poId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this purchase order'));
  return response.json();
}

/**
 * The same lightbox, for the other book (plan section 4.3): the shipping order's own
 * allocation lines and who they are spoken for by. Addressed by NUMBER - an SPO has no
 * purchase order id behind it, and the number is what the link on screen carries.
 *
 * The number is percent-encoded because it carries a slash (`SPO-2026/08-0015`); the
 * route takes the rest of the path as one parameter for exactly that reason.
 */
export async function getOrderInquirySpoDetail(
  spoNumber: string,
): Promise<OrderInquirySpoDetail> {
  const response = await apiFetch(
    `${BASE}/order-inquiries/spo/${encodeURIComponent(spoNumber)}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this shipping order'));
  return response.json();
}

/**
 * The same rows as the list, as the spreadsheet purchasing already reads (AC-I5).
 *
 * Paging is dropped: an export of page two of a filtered set is a file nobody can use.
 */
export async function downloadOrderInquiryXlsx(
  projectId: string,
  params: OrderInquiryListParams = {},
): Promise<Blob> {
  const search = searchParams(params, 25);
  search.delete('page');
  search.delete('limit');
  search.delete('sort');
  search.delete('dir');
  const qs = search.toString();
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/order-inquiry-export${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to export the order inquiry'));
  return response.blob();
}

