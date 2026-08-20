import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  AutoPlaceRequest,
  AutoPlaceResult,
  OrderInquiryDetail,
  OrderInquiryListEnvelope,
  OrderInquiryListParams,
  OrderInquiryPoAllocation,
  OrderInquiryPoCandidate,
  OrderInquiryPoDetail,
  OrderInquiryRow,
  OrderInquirySummary,
  OrderInquiryWorklistEnvelope,
  OrderInquiryWorklistParams,
  OrderInquiryWorklistRow,
  OrderInquiryWorklistSummary,
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

/* --------------------------------------------------------- Place on PO (section G, G2)
 *
 * API CONTRACT (backend section G, reworked G2 20 Aug - placements happen automatically;
 * this dialog is override + audit).
 *
 *   GET  {BASE}/order-inquiry-rows/{rowId}/po-candidates
 *        -> OrderInquiryPoCandidate[], soonest expected_date first, ties by document
 *        sequence. Each candidate carries `default_take` - the cascade's own preview of
 *        what it would take off that line. 409 when the row is not a raised
 *        ORDER/RESERVE & ORDER row.
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/place-on-po  { po_line_id }
 *        -> OrderInquiryRowOut, state 'placed'. The original single-line shape,
 *        unchanged: one line, no split. 409 naming the shortfall when the line's
 *        remaining balance cannot cover the row.
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/place-on-po  { allocations: [{po_line_id, qty}] }
 *        -> OrderInquiryRowOut, the FIRST row the call touched (the row reused on full
 *        coverage, the first new split row on a partial one). A row several lines cover
 *        SPLITS server-side - refetch the rows list to see every row the call wrote.
 *        409 `order_inquiry_over_allocated` when the allocations total more than the
 *        row's own quantity; 409 `order_inquiry_po_line_short` naming the line that
 *        cannot cover what was asked of it.
 *
 *   POST {BASE}/order-inquiry-rows/{rowId}/unplace
 *        -> OrderInquiryRowOut, state back to 'raised'. 409 when the row is not placed.
 *        Works on a split row exactly as on an unsplit one.
 *
 *   POST {BASE}/order-inquiries/auto-place  { product_ids? }
 *        -> AutoPlaceResult { placed_rows, allocations, products_touched }. Runs the
 *        cascade now, over every raised row of the named products (or of every product
 *        carrying one, when `product_ids` is omitted). Idempotent - a second call with
 *        the same products places nothing further.
 *
 * Permission is the same as `mark`: `projects.order_inquiry.action`.
 */

export async function getOrderInquiryPoCandidates(
  rowId: string,
): Promise<OrderInquiryPoCandidate[]> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/po-candidates`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load purchase order lines'));
  return response.json();
}

/** Tag a raised row onto one outstanding PO line - the captain's "quantity to be ordered
 * is deducted". The original single-line shape. */
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
    throw new Error(await extractApiError(response, 'Failed to place this row on a purchase order'));
  return response.json();
}

/**
 * Tag a raised row across one or more outstanding PO lines - the cascade shape (G2), one
 * call. The row may split server-side; the caller reads back the FIRST row the call
 * touched and refetches the rows list to see the rest.
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
    throw new Error(await extractApiError(response, 'Failed to place this row on a purchase order'));
  return response.json();
}

/** Untag: the row goes back to raised. Works on a split row exactly as on an unsplit one. */
export async function unplaceOrderInquiryRow(rowId: string): Promise<OrderInquiryRow> {
  const response = await apiFetch(`${BASE}/order-inquiry-rows/${rowId}/unplace`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to unplace this row'));
  return response.json();
}

/**
 * Run the cascade now (G2 rule 4) - the worklist's "Auto-place". Every raised
 * ORDER/RESERVE & ORDER row of the named products, or of every product carrying one when
 * `product_ids` is omitted, tagged to its own open PO lines, earliest expected date
 * first. Idempotent: a second call with the same products places nothing further.
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
    throw new Error(await extractApiError(response, 'Failed to run the auto-place pass'));
  return response.json();
}

/* ------------------------------------------------ the cross-project worklist
 *
 * API CONTRACT. Written in Phase 1 against a fixture, before any backend existed, and
 * this is what the routes were then built to satisfy.
 *
 *   GET  {BASE}/order-inquiries
 *        query, delivery_month=YYYY-MM, raised_date=YYYY-MM-DD, state, project_id,
 *        supplier_id, page, limit, sort, dir
 *        -> { data: OrderInquiryWorklistRow[], pagination: {total,page,limit}, empty }
 *        sort is a CLOSED set - so_date, so_number, item_code, product_name, qty,
 *        delivery_date, project_customer, supplier, po_number, state, raised_at - and an
 *        unknown value is a 422, never a silent fall back to the default.
 *
 *   GET  {BASE}/order-inquiries/summary
 *        the same filters, no paging
 *        -> { total_rows, total_qty, by_state,
 *             by_month: [{month,label,rows,qty}], suppliers: [], projects: [] }
 *        The totals honour every filter. The three AXES each ignore their own filter on
 *        purpose: they are the screen's controls, and a control that empties itself the
 *        moment it is used cannot be used a second time.
 *
 *   GET  {BASE}/order-inquiries/export
 *        the same filters, no paging -> xlsx, one sheet per delivery month.
 *
 * Rows come from EVERY project and from every adopted AutoCount order, which belongs to
 * no project at all. Permission is `projects.projects.view`, the same read the module
 * already grants.
 *
 * The Schedule matrix (List | Schedule, reworked) is NOT a fourth endpoint: it asks this
 * same list, unpaged (`limit: MATRIX_FETCH_LIMIT` in `OrderInquiriesClient`), and groups
 * the rows client-side by whichever axis and date granularity the reader picked
 * (`_shared/lib/orderInquiryMatrix.ts`). One fetch, one idea of what a row is.
 */

function worklistParams(params: OrderInquiryWorklistParams, limit: number) {
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

