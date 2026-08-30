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
 * The largest page a hand-edited detail URL may ask for, in one place.
 *
 * It is the biggest entry in the DataGrid's own Rows-per-page menu
 * (`DEFAULT_PAGE_SIZES` in `data-grid-pagination.tsx`), and a test holds the two
 * equal. It exists because a detail URL is hand-editable: `?limit=100000`
 * reached the list GET unchallenged and asked the database for the whole table.
 *
 * 100 is the largest page EVERY list route accepts. `MAX_PAGE_LIMIT` in
 * `app/schemas/common.py` is 1000, but the routes do not all use it: 18 declare
 * `le=100` and 16 `le=200`, so a bigger limit is a 422 on those lists. A list
 * whose own route takes more passes its own `sizes` to `DataGridPagination`.
 */
export const MAX_LIST_PAGE_SIZE = 100;

/**
 * Parse a detail-route `URLSearchParams` back into the list query shape the
 * pager and the lists expect. Returns the DataGrid params plus a passthrough map
 * of any extra resource filters present (e.g. assigned_to, status).
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
    pageSize:
      Number.isFinite(limit) && limit > 0
        ? Math.min(limit, MAX_LIST_PAGE_SIZE)
        : 50,
    sorting,
    searchQuery,
    filters,
  };
}

/**
 * Encode the advanced (POST list-query) filter for the detail URL round-trip.
 *
 * A list whose advanced filter is not in the URL cannot have its page rebuilt by
 * the detail page's pager, so the pager would walk the UNFILTERED set. Every list
 * with an advanced filter therefore carries it as `advFilter`.
 */
export function encodeAdvancedFilter(
  filter: unknown | null | undefined,
): string | undefined {
  if (filter == null) return undefined;
  try {
    return encodeURIComponent(JSON.stringify(filter));
  } catch {
    return undefined;
  }
}

/** Decode the advanced filter carried back from a detail URL (invalid -> null). */
export function decodeAdvancedFilter<T = unknown>(raw: string | undefined): T | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(decodeURIComponent(raw)) as {
      op?: string;
      children?: unknown;
    };
    if (
      parsed &&
      typeof parsed === 'object' &&
      (parsed.op === 'and' || parsed.op === 'or') &&
      Array.isArray(parsed.children)
    ) {
      return parsed as T;
    }
  } catch {
    /* ignore malformed / oversized */
  }
  return null;
}
