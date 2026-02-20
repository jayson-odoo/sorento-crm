import { apiFetch } from '@/lib/api';
import type { PickingLinesListResponse } from '../types/pickingLine.types';

export interface PickingLinesListParams {
  page?: number;
  limit?: number;
  query?: string;
  sort?: 'spo_allocation' | 'product' | 'quantity_expected' | 'quantity_picked';
  dir?: 'asc' | 'desc';
}

export async function getPickingLines(
  params: PickingLinesListParams = {},
): Promise<PickingLinesListResponse> {
  const { page = 1, limit = 50, query, sort = 'spo_allocation', dir = 'asc' } = params;
  const searchParams = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort,
    dir,
  });
  if (query?.trim()) searchParams.set('query', query.trim());
  const response = await apiFetch(
    `/api/v1/procurement/picking-lines?${searchParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch picking lines');
  return response.json();
}
