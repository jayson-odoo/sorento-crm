import { apiFetch } from '@/lib/api';
import type { PromotionProductListItem } from '../types/promotionProduct.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getPromotionProductsList(params: DataGridApiFetchParams): Promise<DataGridApiResponse<PromotionProductListItem>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/v1/marketing/promotion-products?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch promotion products');
  return response.json();
}
