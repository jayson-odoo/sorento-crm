import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  OrderInquiryDetail,
  OrderInquiryListEnvelope,
  OrderInquiryListParams,
  OrderInquiryRow,
  OrderInquirySummary,
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
