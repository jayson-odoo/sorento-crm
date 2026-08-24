/**
 * ============================================================================
 * SCM option lists - real bindings for the filter bar + sales-order form
 * ============================================================================
 * SCM has no dedicated option endpoints, so these reuse existing peer routes
 * (all reachable by an admin):
 *   warehouses - derived from GET /scm/dashboard/warehouses
 *   suppliers - derived from GET /scm/dashboard/suppliers
 *   categories - GET /master-data/product-categories/select (value = id)
 *   customers - GET /order-management/customers/select (value = customer_code)
 *   products  - GET /master-data/products/select (value = product_code)
 *   order types - GET /lookup/by-binding?table=sales_orders&column=order_type
 *                 (falls back to a sensible static list when no binding exists)
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { EMPTY_SCM_FILTERS, getSuppliers, getWarehouseHealth } from './scmDashboardService';

export interface Option {
  value: string;
  label: string;
  description?: string;
}

export async function getWarehouseOptions(): Promise<Option[]> {
  const { data } = await getWarehouseHealth(EMPTY_SCM_FILTERS);
  return data.map((w) => ({ value: w.warehouse_code, label: w.warehouse_name }));
}

export async function getSupplierOptions(): Promise<Option[]> {
  const { data } = await getSuppliers(EMPTY_SCM_FILTERS);
  return data.map((s) => ({ value: s.supplier_code, label: s.supplier_name }));
}

export async function getCategoryOptions(): Promise<Option[]> {
  const res = await apiFetch('/api/v1/master-data/product-categories/select');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load categories'));
  const rows = (await res.json()) as { id: string; category_name: string }[];
  return rows.map((c) => ({ value: c.id, label: c.category_name }));
}

export async function getCustomerOptions(): Promise<Option[]> {
  const res = await apiFetch('/api/v1/order-management/customers/select');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load customers'));
  const body = (await res.json()) as {
    data: { customer_code: string; customer_name: string; market_segment_code?: string | null }[];
  };
  // customer_code is not unique in this dataset - dedupe to one option per code.
  const seen = new Set<string>();
  const out: Option[] = [];
  for (const c of body.data) {
    if (seen.has(c.customer_code)) continue;
    seen.add(c.customer_code);
    out.push({
      value: c.customer_code,
      label: c.customer_name,
      description: c.market_segment_code ?? undefined,
    });
  }
  return out;
}

export async function getProductOptions(): Promise<Option[]> {
  const res = await apiFetch('/api/v1/master-data/products/select');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load products'));
  const body = (await res.json()) as {
    data: { product_code: string; product_name: string }[];
  };
  return body.data.map((p) => ({
    value: p.product_code,
    label: `${p.product_code} · ${p.product_name}`,
  }));
}

const STATIC_ORDER_TYPES: Option[] = [
  { value: 'dealer', label: 'Dealer' },
  { value: 'project', label: 'Project' },
];

export async function getOrderTypeOptions(): Promise<Option[]> {
  const res = await apiFetch(
    '/api/v1/lookup/by-binding?table=sales_orders&column=order_type',
  );
  if (!res.ok) return STATIC_ORDER_TYPES;
  const body = (await res.json()) as { options?: { value: string; label: string }[] };
  const opts = (body.options ?? []).map((o) => ({ value: o.value, label: o.label }));
  return opts.length ? opts : STATIC_ORDER_TYPES;
}
