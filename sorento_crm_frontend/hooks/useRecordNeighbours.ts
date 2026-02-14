'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface RecordNeighboursResult {
  prev_id: string | null;
  next_id: string | null;
}

/**
 * Generic hook to fetch prev/next record IDs from a backend neighbours endpoint.
 * Use this with RecordNavigation for consistent chevron navigation across detail views.
 *
 * @param apiPath - Full path to the neighbours endpoint, e.g. '/api/v1/procurement/purchase-requests/neighbours'
 * @param currentId - Current record ID (null to disable the query)
 * @param queryParams - Optional query params, e.g. { request_type: 'purchase_request' }
 */
export function useRecordNeighbours(
  apiPath: string,
  currentId: string | null,
  queryParams?: Record<string, string | undefined>,
): RecordNeighboursResult {
  const params = new URLSearchParams();
  if (currentId) params.set('id', currentId);
  if (queryParams) {
    Object.entries(queryParams).forEach(([k, v]) => {
      if (v != null && v !== '') params.set(k, v);
    });
  }
  const queryString = params.toString();
  const url = queryString ? `${apiPath}?${queryString}` : apiPath;

  const { data } = useQuery({
    queryKey: ['record-neighbours', apiPath, currentId, queryParams],
    queryFn: async (): Promise<RecordNeighboursResult> => {
      const response = await apiFetch(url);
      if (!response.ok) return { prev_id: null, next_id: null };
      return response.json();
    },
    enabled: !!currentId,
  });

  return data ?? { prev_id: null, next_id: null };
}
