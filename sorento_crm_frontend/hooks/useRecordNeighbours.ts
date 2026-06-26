'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** Backend (snake_case) shape returned by every `/neighbours` endpoint. */
export interface RecordNeighboursResponse {
  total: number;
  index: number | null;
  prev_id: string | null;
  next_id: string | null;
}

/** Resolved neighbour data (camelCase). */
interface RecordNeighboursData {
  prevId: string | null;
  nextId: string | null;
  index: number | null;
  total: number;
}

/** Hook surface consumed by `RecordNavigation` in IDs mode (data + query state). */
export interface RecordNeighboursResult extends RecordNeighboursData {
  isLoading: boolean;
}

const EMPTY: RecordNeighboursData = {
  prevId: null,
  nextId: null,
  index: null,
  total: 0,
};

/**
 * Generic hook to fetch prev/next neighbours from a backend `/neighbours` endpoint
 * scoped to the active filtered+sorted+searched list set.
 *
 * Layering: UI -> this hook -> `apiFetch` (lib/api-client). Resource feature
 * services compose this via a thin `useXxxNeighbours` wrapper that maps the list
 * query into `listParams` using `buildDataGridParams`.
 *
 * @param apiPath   Full path to the neighbours endpoint, e.g.
 *                  '/api/v1/complaints-management/complaints/neighbours'
 * @param currentId Current record id (null/empty disables the query)
 * @param listParams The same list query params the list page sends (built with
 *                  `buildDataGridParams`). `page`/`limit` are ignored by the backend.
 */
export function useRecordNeighbours(
  apiPath: string,
  currentId: string | null,
  listParams?: URLSearchParams | Record<string, string | undefined>,
): RecordNeighboursResult {
  const params = new URLSearchParams();
  if (currentId) params.set('id', currentId);
  if (listParams) {
    const entries =
      listParams instanceof URLSearchParams
        ? Array.from(listParams.entries())
        : Object.entries(listParams);
    for (const [k, v] of entries) {
      if (k === 'id') continue; // current id is set explicitly above
      if (v != null && v !== '') params.set(k, String(v));
    }
  }
  const queryString = params.toString();
  const url = queryString ? `${apiPath}?${queryString}` : apiPath;

  const { data, isLoading } = useQuery({
    queryKey: ['record-neighbours', apiPath, currentId, queryString],
    queryFn: async (): Promise<RecordNeighboursData> => {
      const response = await apiFetch(url);
      if (!response.ok) {
        throw new Error(
          await extractApiError(response, 'Failed to load record navigation'),
        );
      }
      const json: RecordNeighboursResponse = await response.json();
      return {
        prevId: json.prev_id ?? null,
        nextId: json.next_id ?? null,
        index: json.index ?? null,
        total: json.total ?? 0,
      };
    },
    enabled: !!currentId,
    staleTime: 30 * 1000,
  });

  return { ...(data ?? EMPTY), isLoading };
}
