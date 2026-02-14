import { apiFetch } from '@/lib/api';
import type {
  StockInquiry,
  StockInquiryFormData,
  StockInquiryDetail,
} from '../types/stockInquiry.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export async function getStockInquiries(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<StockInquiry>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch stock inquiries');
  return response.json();
}

export async function getStockInquiry(id: string): Promise<StockInquiryDetail> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`);
  if (!response.ok) throw new Error('Failed to fetch stock inquiry');
  return response.json();
}

export async function getStockInquiryNeighbours(
  id: string,
): Promise<{ prev_id: string | null; next_id: string | null }> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/neighbours?id=${encodeURIComponent(id)}`,
  );
  if (!response.ok) return { prev_id: null, next_id: null };
  return response.json();
}

export async function createStockInquiry(
  data: StockInquiryFormData,
): Promise<StockInquiry> {
  const response = await apiFetch('/api/v1/procurement/stock-inquiries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create stock inquiry' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStockInquiry(
  id: string,
  data: Partial<StockInquiryFormData>,
): Promise<StockInquiry> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update stock inquiry' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStockInquiryAndReply(
  id: string,
  data: Partial<StockInquiryFormData>,
): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/update-and-reply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update and reply' }));
    throw new Error(error.detail || error.message || 'Failed to update and reply');
  }
  return response.json();
}

export async function deleteStockInquiry(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete stock inquiry' }));
    throw new Error(error.message);
  }
}
