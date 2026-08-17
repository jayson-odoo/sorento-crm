import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { PromotionType, PromotionTypeFormData } from '../types/promotionType.types';

const BASE = '/api/marketing/promotion-types';

export async function getPromotionTypes(): Promise<DataGridApiResponse<PromotionType>> {
  const response = await apiFetch(`${BASE}/`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch promotion types'));
  }
  return response.json();
}

export async function getPromotionType(id: string): Promise<PromotionType | null> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch promotion type'));
  }
  return response.json();
}

export async function createPromotionType(data: PromotionTypeFormData): Promise<PromotionType> {
  const response = await apiFetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create promotion type'));
  }
  return response.json();
}

export async function updatePromotionType(
  id: string,
  data: Partial<PromotionTypeFormData>,
): Promise<PromotionType> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update promotion type'));
  }
  return response.json();
}

export async function deletePromotionType(id: string): Promise<{ promotions_unclassified?: number }> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete promotion type'));
  }
  return response.json();
}
