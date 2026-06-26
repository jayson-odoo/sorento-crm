import { apiFetch } from '@/lib/api';
import { promotionFormDateToApiYyyyMmDd } from '@/lib/helpers';
import type {
  Promotion,
  PromotionFormData,
  PromotionDetail,
  PromotionProduct,
  PromotionGroup,
  FocTier,
} from '../types/promotion.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type PromotionsListParams = DataGridApiFetchParams & {
  status?: string;
  date_from?: string;
  date_to?: string;
  user_type?: string;
  attachment_state?: 'unlinked' | 'linked_to_trashed' | 'unlinked_or_trashed';
};

/**
 * Path of the promotions neighbours endpoint. Consumed by `usePromotionNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract:
 *   GET /api/v1/marketing/promotions/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, status, user_type, attachment_state, sort, dir).
 *                 page/limit are ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const PROMOTION_NEIGHBOURS_PATH =
  '/api/v1/marketing/promotions/neighbours';

export async function getPromotions(
  params: PromotionsListParams,
): Promise<DataGridApiResponse<Promotion>> {
  const { pageIndex, pageSize, sorting, searchQuery, status, date_from, date_to, user_type, attachment_state } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(status ? { status } : {}),
    ...(date_from ? { date_from } : {}),
    ...(date_to ? { date_to } : {}),
    ...(user_type ? { user_type } : {}),
    ...(attachment_state ? { attachment_state } : {}),
  });
  const response = await apiFetch(`/api/v1/marketing/promotions?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch promotions');
  return response.json();
}

export async function getPromotion(id: string): Promise<PromotionDetail> {
  const response = await apiFetch(
    `/api/v1/marketing/promotions/${id}?include_products=true`,
  );
  if (!response.ok) throw new Error('Failed to fetch promotion');
  return response.json();
}

function serializePromotionWriteBody(data: Partial<PromotionFormData>): Record<string, unknown> {
  const { start_date, end_date, ...rest } = data;
  const out: Record<string, unknown> = { ...rest };
  const s = promotionFormDateToApiYyyyMmDd(start_date);
  if (s !== undefined) out.start_date = s;
  const e = promotionFormDateToApiYyyyMmDd(end_date);
  if (e !== undefined) out.end_date = e;
  return out;
}

export async function createPromotion(data: PromotionFormData): Promise<Promotion> {
  const response = await apiFetch('/api/v1/marketing/promotions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serializePromotionWriteBody(data)),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updatePromotion(id: string, data: Partial<PromotionFormData>): Promise<Promotion> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serializePromotionWriteBody(data)),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deletePromotion(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete promotion' }));
    throw new Error(error.message);
  }
}

export async function bulkDeletePromotions(ids: string[]): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/marketing/promotions/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to bulk delete promotions' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to bulk delete promotions');
  }
  return response.json();
}

export async function bulkUpdateAccessLevels(
  ids: string[],
  access_levels: string[],
): Promise<{ message: string; updated_count: number }> {
  const response = await apiFetch('/api/v1/marketing/promotions/bulk', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, access_levels }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update access levels' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to update access levels');
  }
  return response.json();
}

export async function getPromotionProducts(promotionId: string): Promise<PromotionProduct[]> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/products`);
  if (!response.ok) throw new Error('Failed to fetch promotion products');
  return response.json();
}

export async function getPromotionsByProductId(productId: string): Promise<PromotionProduct[]> {
  const params = new URLSearchParams({ product_id: productId, limit: '100', page: '1' });
  const response = await apiFetch(`/api/v1/marketing/promotion-products?${params.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch promotions for product');
  const payload = await response.json();
  return (payload?.data ?? []) as PromotionProduct[];
}

export async function createPromotionGroup(
  promotionId: string,
  data: {
    group_name: string;
    sort_order?: number | null;
    foc_tiers?: FocTier[] | null;
  },
): Promise<PromotionGroup> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? err.message ?? 'Failed to create promotion group');
  }
  return response.json();
}

export async function updatePromotionGroup(
  promotionId: string,
  groupId: string,
  data: {
    group_name?: string;
    sort_order?: number | null;
    foc_tiers?: FocTier[] | null;
  },
): Promise<PromotionGroup> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/groups/${groupId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? err.message ?? 'Failed to update promotion group');
  }
  return response.json();
}

export async function deletePromotionGroup(
  promotionId: string,
  groupId: string,
): Promise<{ message: string; deleted_product_lines?: number }> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/groups/${groupId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? err.message ?? 'Failed to delete promotion group');
  }
  return response.json();
}

export async function addPromotionProduct(
  promotionId: string,
  productId: string,
  promotionPrice?: number,
  promotionGroupId?: string,
  dealerDiscountPercent?: number | null,
): Promise<PromotionProduct> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      product_id: productId,
      promotion_price: promotionPrice,
      ...(promotionGroupId ? { promotion_group_id: promotionGroupId } : {}),
      ...(dealerDiscountPercent !== undefined ? { dealer_discount_percent: dealerDiscountPercent } : {}),
    }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to add product to promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

/** `lineId` is promotion_products.id (junction row); required when the same SKU appears in multiple groups. */
export async function removePromotionProduct(promotionId: string, lineId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/products/${lineId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to remove product from promotion' }));
    throw new Error(error.message);
  }
}

export async function updatePromotionProductPrice(
  promotionId: string,
  lineId: string,
  args: {
    promotionPrice: number;
    dealerDiscountPercent: number | null;
    listPrice: number;
  },
): Promise<PromotionProduct> {
  const response = await apiFetch(`/api/v1/marketing/promotions/${promotionId}/products/${lineId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      promotion_price: args.promotionPrice,
      dealer_discount_percent: args.dealerDiscountPercent,
      list_price: args.listPrice,
    }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update promotion product price' }));
    throw new Error(error.message);
  }
  return response.json();
}
