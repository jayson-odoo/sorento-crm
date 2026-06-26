/**
 * Shared helpers for carrying a list page's active query (search/sort/filters)
 * into the detail route URL, so the detail page's prev/next pager can walk the
 * exact same filtered+sorted set the user navigated from.
 *
 * The detail URL search string uses the SAME param names as the list GET
 * (page/limit/sort/dir/query + per-resource filters), built with
 * `buildDataGridParams`, so the neighbours hook can forward them verbatim.
 *
 * See docs/plans/PLAN-record-navigation-standardization.md §3.3.
 */

import type { SortingState } from '@tanstack/react-table';
import { buildDataGridParams } from '@/lib/api-client';

/**
 * Serialize a DataGrid list query + extra filters into a URL search string
 * (no leading `?`). Empty/undefined extras are dropped.
 */
export function buildDetailSearch(
  params: {
    pageIndex: number;
    pageSize: number;
    sorting?: SortingState;
    searchQuery?: string;
  },
  extra?: Record<string, string | number | boolean | undefined | null>,
): string {
  return buildDataGridParams(params, extra).toString();
}

/**
 * Parse a detail-route `URLSearchParams` back into the list query shape the
 * neighbours hook expects. Returns the DataGrid params plus a passthrough map of
 * any extra resource filters present (e.g. assigned_to, status).
 */
export function parseDetailSearch(searchParams: URLSearchParams): {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  filters: Record<string, string>;
} {
  const page = Number(searchParams.get('page') || '1');
  const limit = Number(searchParams.get('limit') || '50');
  const sort = searchParams.get('sort') || '';
  const dir = searchParams.get('dir') || 'asc';
  const searchQuery = searchParams.get('query') || '';

  const sorting: SortingState = sort ? [{ id: sort, desc: dir === 'desc' }] : [];

  const reserved = new Set(['page', 'limit', 'sort', 'dir', 'query', 'id']);
  const filters: Record<string, string> = {};
  for (const [k, v] of searchParams.entries()) {
    if (!reserved.has(k) && v !== '') filters[k] = v;
  }

  return {
    pageIndex: Number.isFinite(page) && page > 0 ? page - 1 : 0,
    pageSize: Number.isFinite(limit) && limit > 0 ? limit : 50,
    sorting,
    searchQuery,
    filters,
  };
}
