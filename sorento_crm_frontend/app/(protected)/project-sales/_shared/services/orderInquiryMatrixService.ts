/**
 * The Schedule matrix's own read (S3, PLAN-scm-oi-worklist-excel-parity.md).
 *
 * API CONTRACT:
 *
 *   GET {BASE}/order-inquiries/matrix?axis=product|sales_order|customer|agent
 *       &by=day|week|month|year&<every /order-inquiries list filter>
 *     -> { data: [{ axis_key, axis_label, period, qty, buy, po, spo, rows }] }
 *
 *   One GROUP BY over the same filtered set the list reads - `axis_key`/`axis_label` the
 *   row's value on the chosen axis, `period` the ISO date the bucket starts on (week
 *   buckets start Monday, month/year bucket on the first of the month/year), `qty` the
 *   summed still-owed quantity, `buy`/`po`/`spo` the R-F stage sums, `rows` the COUNT of
 *   worklist rows summed into the cell (never the rows themselves - the drilldown asks
 *   the list again, scoped to this cell's own axis + period). No row cap: the old
 *   client-side matrix built off an unpaged `limit=1000` list fetch, which a
 *   delivery-filtered worklist had already exceeded on prod (PLAN section 0).
 *
 *   Same permission as the list (`projects.projects.view`) - reading the schedule is
 *   reading the worklist a second way, not a second grant. `axis`/`by` outside the
 *   closed set above is a 422, never a silent fall back.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { worklistParams } from './orderInquiryService';
import type {
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryMatrixParams,
} from '../types/orderInquiry.types';

const BASE = '/api/v1/project-sales';

/** The last day a period covers - what a cell's drilldown asks the list for as
 * `delivery_to`. Client-side only: the server never has to answer it, since the
 * drilldown re-asks the list rather than reading rows back out of the matrix. */
export function periodEnd(period: string, by: OrderInquiryMatrixGranularity): string {
  const date = new Date(`${period}T00:00:00`);
  if (by === 'day') return period;
  if (by === 'week') {
    const end = new Date(date);
    end.setDate(end.getDate() + 6);
    return end.toISOString().slice(0, 10);
  }
  if (by === 'month') {
    const end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
    return end.toISOString().slice(0, 10);
  }
  const end = new Date(date.getFullYear(), 11, 31);
  return end.toISOString().slice(0, 10);
}

/**
 * The matrix cells for one axis/granularity/filter set. `data` only, matching the
 * envelope every other list/summary read here already returns.
 */
export async function getOrderInquiryMatrix(
  params: OrderInquiryMatrixParams,
): Promise<{ data: OrderInquiryMatrixCell[] }> {
  const search = worklistParams(params, 1);
  search.delete('page');
  search.delete('limit');
  search.delete('sort');
  search.delete('dir');
  search.set('axis', params.axis);
  search.set('by', params.by);
  const response = await apiFetch(`${BASE}/order-inquiries/matrix?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the schedule'));
  const body = (await response.json()) as { data?: OrderInquiryMatrixCell[] };
  return { data: Array.isArray(body.data) ? body.data : [] };
}
