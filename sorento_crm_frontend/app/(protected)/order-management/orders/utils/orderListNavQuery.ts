import type { SortingState } from '@tanstack/react-table';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

/** Mirrors Orders list state so order detail prev/next matches the same filtered API query. */
export type OrderListNavState = {
  pageIndex: number;
  pageSize: number;
  orderStatusId: string | undefined;
  hasOrderLines: 'all' | 'yes' | 'no';
  searchQuery: string;
  sorting: SortingState;
  /** When set, must be preserved on detail URLs so navigation uses POST list-query (same as list). */
  advancedFilter?: ListQueryFilterGroup | null;
};

const DEFAULT_SORT: SortingState = [{ id: 'created_at', desc: true }];

export function orderListNavDefaults(): OrderListNavState {
  return {
    pageIndex: 0,
    pageSize: 50,
    orderStatusId: undefined,
    hasOrderLines: 'all',
    searchQuery: '',
    sorting: DEFAULT_SORT,
    advancedFilter: null,
  };
}

/** Append list context to order detail URLs (prev/next preserve filters). */
export function appendOrderListNavToParams(params: URLSearchParams, state: OrderListNavState): void {
  params.set('page', String(state.pageIndex));
  params.set('pageSize', String(state.pageSize));
  if (state.orderStatusId) {
    params.set('orderStatusId', state.orderStatusId);
  }
  if (state.hasOrderLines && state.hasOrderLines !== 'all') {
    params.set('hasOrderLines', state.hasOrderLines);
  }
  if (state.searchQuery.trim()) {
    params.set('q', state.searchQuery.trim());
  }
  const sort = state.sorting?.[0];
  if (sort?.id) {
    params.set('sort', sort.id);
    params.set('sortDesc', sort.desc ? '1' : '0');
  }
  if (state.advancedFilter != null) {
    try {
      params.set('advFilter', encodeURIComponent(JSON.stringify(state.advancedFilter)));
    } catch {
      /* ignore oversized / invalid */
    }
  }
}

export function buildOrderDetailSearch(state: OrderListNavState): string {
  const p = new URLSearchParams();
  appendOrderListNavToParams(p, state);
  const s = p.toString();
  return s ? `?${s}` : '';
}

/** Parse order detail ?query= back into list nav state (invalid values fall back to defaults). */
export function parseOrderListNavFromSearchParams(searchParams: URLSearchParams): OrderListNavState {
  const d = orderListNavDefaults();
  const pageRaw = searchParams.get('page');
  const sizeRaw = searchParams.get('pageSize');
  const pageIndex = pageRaw != null ? Number.parseInt(pageRaw, 10) : d.pageIndex;
  const pageSize = sizeRaw != null ? Number.parseInt(sizeRaw, 10) : d.pageSize;
  const orderStatusId = searchParams.get('orderStatusId')?.trim() || undefined;
  const hol = searchParams.get('hasOrderLines')?.trim().toLowerCase();
  const hasOrderLines =
    hol === 'yes' || hol === 'no' ? hol : d.hasOrderLines;
  const q = searchParams.get('q') ?? '';
  const sortId = searchParams.get('sort')?.trim();
  const sortDescRaw = searchParams.get('sortDesc');
  const sorting: SortingState =
    sortId && sortId.length > 0
      ? [{ id: sortId, desc: sortDescRaw === '1' || sortDescRaw === 'true' }]
      : d.sorting;

  let advancedFilter: ListQueryFilterGroup | null = null;
  const rawAdv = searchParams.get('advFilter');
  if (rawAdv) {
    try {
      const parsed = JSON.parse(decodeURIComponent(rawAdv)) as ListQueryFilterGroup;
      if (parsed && typeof parsed === 'object' && (parsed.op === 'and' || parsed.op === 'or') && Array.isArray(parsed.children)) {
        advancedFilter = parsed;
      }
    } catch {
      advancedFilter = null;
    }
  }

  return {
    pageIndex: Number.isFinite(pageIndex) && pageIndex >= 0 ? pageIndex : d.pageIndex,
    pageSize: Number.isFinite(pageSize) && pageSize > 0 ? Math.min(pageSize, 500) : d.pageSize,
    orderStatusId: orderStatusId || undefined,
    hasOrderLines,
    searchQuery: q,
    sorting,
    advancedFilter,
  };
}
