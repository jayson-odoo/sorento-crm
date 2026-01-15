import { apiFetch } from '@/lib/api';
import type { PromotionAttachment, PromotionAttachmentFormData } from '../types/promotionAttachment.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getPromotionAttachments(params: DataGridApiFetchParams & { promotion_id?: string; attachment_id?: string }): Promise<DataGridApiResponse<PromotionAttachment>> {
  const { pageIndex, pageSize, sorting, searchQuery, promotion_id, attachment_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(promotion_id ? { promotion_id } : {}),
    ...(attachment_id ? { attachment_id } : {}),
  });
  const response = await apiFetch(`/api/v1/marketing/promotion-attachments?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch promotion attachments');
  return response.json();
}

export async function getPromotionAttachment(id: string): Promise<PromotionAttachment> {
  const response = await apiFetch(`/api/v1/marketing/promotion-attachments/${id}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to fetch promotion attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function createPromotionAttachment(data: PromotionAttachmentFormData): Promise<PromotionAttachment> {
  const response = await apiFetch('/api/v1/marketing/promotion-attachments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create promotion attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updatePromotionAttachment(id: string, data: Partial<PromotionAttachmentFormData>): Promise<PromotionAttachment> {
  const response = await apiFetch(`/api/v1/marketing/promotion-attachments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update promotion attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deletePromotionAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/marketing/promotion-attachments/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete promotion attachment' }));
    throw new Error(error.message);
  }
}

export async function getPromotionAttachmentsByPromotion(promotionId: string): Promise<PromotionAttachment[]> {
  const response = await apiFetch(`/api/v1/marketing/promotion-attachments/promotion/${promotionId}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to fetch promotion attachments' }));
    throw new Error(error.message || 'Failed to fetch promotion attachments');
  }
  return response.json();
}
