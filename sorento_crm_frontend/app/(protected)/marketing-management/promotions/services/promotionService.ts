import { apiFetch } from '@/lib/api';
import type { Promotion, PromotionFormData, PromotionDetail, PromotionProduct } from '../types/promotion.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getPromotions(params: DataGridApiFetchParams & { promo_type?: string; status?: string; date_from?: string; date_to?: string }): Promise<DataGridApiResponse<Promotion>> {
  const { pageIndex, pageSize, sorting, searchQuery, promo_type, status, date_from, date_to } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(promo_type ? { promo_type } : {}),
    ...(status ? { status } : {}),
    ...(date_from ? { date_from } : {}),
    ...(date_to ? { date_to } : {}),
  });
  const response = await apiFetch(`/api/marketing/promotions?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch promotions');
  return response.json();
}

export async function getPromotion(id: string): Promise<PromotionDetail> {
  const response = await apiFetch(`/api/marketing/promotions/${id}`);
  if (!response.ok) throw new Error('Failed to fetch promotion');
  return response.json();
}

export async function createPromotion(data: PromotionFormData): Promise<Promotion> {
  const response = await apiFetch('/api/marketing/promotions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updatePromotion(id: string, data: Partial<PromotionFormData>): Promise<Promotion> {
  const response = await apiFetch(`/api/marketing/promotions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deletePromotion(id: string): Promise<void> {
  const response = await apiFetch(`/api/marketing/promotions/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete promotion' }));
    throw new Error(error.message);
  }
}

export async function getPromotionProducts(promotionId: string): Promise<PromotionProduct[]> {
  const response = await apiFetch(`/api/marketing/promotions/${promotionId}/products`);
  if (!response.ok) throw new Error('Failed to fetch promotion products');
  return response.json();
}

export async function addPromotionProduct(promotionId: string, productId: string, promotionPrice?: number): Promise<PromotionProduct> {
  const response = await apiFetch(`/api/marketing/promotions/${promotionId}/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, promotion_price: promotionPrice }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to add product to promotion' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function removePromotionProduct(promotionId: string, productId: string): Promise<void> {
  const response = await apiFetch(`/api/marketing/promotions/${promotionId}/products/${productId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to remove product from promotion' }));
    throw new Error(error.message);
  }
}

export async function updatePromotionProductPrice(promotionId: string, productId: string, promotionPrice: number): Promise<PromotionProduct> {
  const response = await apiFetch(`/api/marketing/promotions/${promotionId}/products/${productId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ promotion_price: promotionPrice }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update promotion product price' }));
    throw new Error(error.message);
  }
  return response.json();
}
