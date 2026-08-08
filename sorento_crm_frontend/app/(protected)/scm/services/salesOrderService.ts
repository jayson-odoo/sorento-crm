/**
 * ============================================================================
 * SALES ORDERS (M1-D14) — real API bindings (Phase 2 / M1 CP2b)
 * ============================================================================
 * Mounted under `require_module_enabled_with_api_key("scm")` at
 * `/api/v1/scm/sales-orders`. Reads gate on `scm.dashboard.view`; writes gate on
 * `scm.reorder.run`. No UUIDs surfaced — SO identified by so_number in the UI,
 * addressed by id in the path. `uom` is display-only (product base UOM) and is
 * NOT sent on write; the BE stamps it from the product.
 *
 *   GET    /sales-orders            list (page/limit/sort/dir/query/status/priority/source,
                                   date_from/date_to/customer_id/outstanding)
 *   GET    /sales-orders/{id}       single
 *   POST   /sales-orders            create (order_type, customer_code, priority,
 *                                   requested_delivery_date?, lines:[{sku,qty_ordered}])
 *   PUT    /sales-orders/{id}       update (partial)
 *   DELETE /sales-orders/{id}       hard delete (204)
 *   POST   /sales-orders/{id}/create-do   → { sales_order, do_number }
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { SalesOrder, SalesOrderFormData } from '../types/scm.types';

const BASE = '/api/v1/scm/sales-orders';

export interface SalesOrderListQuery {
  pageIndex: number;
  pageSize: number;
  sortField?: string;
  sortDir?: 'asc' | 'desc';
  searchQuery?: string;
  status?: string | null;
  priority?: string | null;
  /** Where the order came from: 'inquiry' | 'upload' | 'manual'. Omit for all. */
  source?: string | null;
  /** Order date, inclusive of both ends. ISO `yyyy-mm-dd`. */
  dateFrom?: string | null;
  dateTo?: string | null;
  customerId?: string | null;
  /** Keep only orders with quantity still owed. `false` narrows nothing. */
  outstanding?: boolean;
}

/** Strip the display-only `uom` from each line — the BE derives it. */
function toWritePayload(data: SalesOrderFormData) {
  return {
    order_type: data.order_type,
    customer_code: data.customer_code,
    priority: data.priority,
    requested_delivery_date: data.requested_delivery_date ?? null,
    lines: data.lines.map((l) => ({ sku: l.sku, qty_ordered: l.qty_ordered })),
  };
}

export async function getSalesOrders(
  params: SalesOrderListQuery,
): Promise<DataGridApiResponse<SalesOrder>> {
  const sorting = params.sortField
    ? [{ id: params.sortField, desc: params.sortDir === 'desc' }]
    : undefined;
  const sp = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting,
      searchQuery: params.searchQuery,
    },
    {
      status: params.status ?? undefined,
      priority: params.priority ?? undefined,
      source: params.source ?? undefined,
      date_from: params.dateFrom || undefined,
      date_to: params.dateTo || undefined,
      customer_id: params.customerId || undefined,
      // Only when ON. Sending `outstanding=false` would put a param on the URL that means
      // "no filter", which then rides into the detail URL and reads as an active filter.
      outstanding: params.outstanding ? 'true' : undefined,
    },
  );
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load sales orders'));
  return res.json();
}

/** One sales order with its lines. `linked_purchase_orders` is a LIST-only field. */
export async function getSalesOrder(id: string): Promise<SalesOrder> {
  const res = await apiFetch(`${BASE}/${id}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the sales order'));
  return res.json();
}

export async function createSalesOrder(data: SalesOrderFormData): Promise<SalesOrder> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toWritePayload(data)),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create sales order'));
  return res.json();
}

export async function updateSalesOrder(
  id: string,
  data: SalesOrderFormData,
): Promise<SalesOrder> {
  const res = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toWritePayload(data)),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update sales order'));
  return res.json();
}

export async function deleteSalesOrder(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete sales order'));
}

export async function createDoFromSalesOrder(
  id: string,
): Promise<{ sales_order: SalesOrder; do_number: string }> {
  const res = await apiFetch(`${BASE}/${id}/create-do`, { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create delivery order'));
  return res.json();
}
