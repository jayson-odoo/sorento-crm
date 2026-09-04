'use client';

/**
 * Prev/next that walks the LIST PAGE the user came from, out of the React Query
 * cache the list already filled.
 *
 * ## The data contract an entity must satisfy
 *
 * The detail URL names the page: `?page=2&limit=50&sort=created_at&dir=desc&query=abc`
 * plus whatever extra filters the list put there (written by the DataGrid's
 * `rowHref` -> `appendListState`, parsed back by `parseDetailSearch`). From that
 * the pager rebuilds `ListPagerParams` and asks the entity for two things:
 *
 * - `listQueryKey(params)` - the SAME React Query key the list used for that page.
 *   Same key = the rows are already in the cache and the pager issues NO request.
 *   The list and the pager must therefore build their key through one shared
 *   function (see `app/(protected)/<module>/<entity>/lib/listQuery.ts`); a key the
 *   pager merely "looks like" is a silent cache miss and a second identical fetch.
 * - `fetchPage(params)` - how to fetch that page when the cache has no entry
 *   (deep link, refresh, or stepping across a page boundary). It must return
 *   `{ data: [{ id }], pagination: { total } }`, which is what every list GET in
 *   this app already returns (`DataGridApiResponse`).
 *
 * A filter the list keeps but does NOT write into the detail URL cannot be
 * rebuilt here, so its key will miss and the pager will page the unfiltered set.
 * Every filter that narrows the list must ride in `rowHref`.
 *
 * ## Behaviour
 *
 * - Position is `items.findIndex(id)` within the cached page; the counter reads
 *   "n / rows on this page".
 * - Previous on the first row of page N>1 fetches page N-1 and lands on its LAST
 *   row; Next on the last row fetches page N+1 and lands on its FIRST row. Both
 *   push a URL naming the new page, so the pager stays consistent after the step.
 * - Disabled at the absolute ends (page 1 row 1, last page last row), and while a
 *   boundary step is in flight, so a second click cannot start a second fetch.
 * - A boundary page that comes back EMPTY (the rows were deleted since the list
 *   was cached, or `total` is stale) is an end, not a no-op: that direction goes
 *   dead rather than swallowing every further click in silence.
 * - The record is not on the page (deep link into a filtered set, or it was
 *   deleted): `visible` is false and the caller renders nothing. Back still works.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { buildDetailSearch, parseDetailSearch } from '@/lib/listNavQuery';
import { usePrefetchOnce } from '@/hooks/usePrefetchOnce';

/** The list query a detail URL describes. */
export interface ListPagerParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  /** Extra list filters carried in the URL (order_status_id, roleId, ...). */
  filters: Record<string, string>;
}

/**
 * What a list GET returns.
 *
 * Two shapes exist in this app and both are read here rather than adapted at
 * each call site: the DataGrid one (`pagination.total`) and the offset-paged SCM
 * one (`total` at the top level, e.g. proforma invoices).
 */
export interface ListPagerPage {
  data: Array<{ id: string }>;
  pagination?: { total: number };
  total?: number;
}

export interface UseListPagerOptions {
  /** Must be the key the LIST used for this page. Build both from one function. */
  listQueryKey: (params: ListPagerParams) => QueryKey;
  fetchPage: (params: ListPagerParams) => Promise<ListPagerPage>;
  /** Detail route base, e.g. `/order-management/orders`. */
  detailPath: string;
  currentId: string;
  /**
   * Where a step lands, when it is not the record's detail page.
   *
   * The five edit forms that carry a pager (customer, product, supplier,
   * promotion, complaint) step between EDIT screens, so they pass this rather
   * than sending an editing user to a read-only page.
   */
  hrefFor?: (id: string, search: string) => string;
}

export interface UseListPagerResult {
  /** False when the record is not on the page named by the URL. Render nothing. */
  visible: boolean;
  /** 1-based position on this page, or null while it is unknown. */
  index: number | null;
  /** Rows on this page. */
  total: number;
  hasPrevious: boolean;
  hasNext: boolean;
  goPrevious: () => void;
  goNext: () => void;
  isLoading: boolean;
}

/**
 * The href a step lands on: the record, plus the page it now sits on.
 *
 * `from` (M5-07) names the id itself, so a reader who steps prev/next three
 * times and then hits Back is restored to the row they actually END on, not
 * the one they started from.
 */
function stepHref(
  detailPath: string,
  id: string,
  params: ListPagerParams,
  hrefFor?: (id: string, search: string) => string,
): string {
  const search = buildDetailSearch(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting: params.sorting,
      searchQuery: params.searchQuery,
    },
    { ...params.filters, from: id },
  );
  if (hrefFor) return hrefFor(id, search);
  return `${detailPath}/${id}${search ? `?${search}` : ''}`;
}

export function useListPager({
  listQueryKey,
  fetchPage,
  detailPath,
  currentId,
  hrefFor,
}: UseListPagerOptions): UseListPagerResult {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const prefetchOnce = usePrefetchOnce();
  const [stepping, setStepping] = useState(false);
  // The direction whose neighbouring page came back empty. `total` said there was
  // more, the fetch says there is not, and the fetch is the newer answer.
  const [deadEnd, setDeadEnd] = useState<'previous' | 'next' | null>(null);

  const searchKey = searchParams.toString();
  // A new record or a new page is a fresh question: the old dead end says nothing
  // about it.
  useEffect(() => setDeadEnd(null), [searchKey, currentId]);
  const params = useMemo<ListPagerParams>(
    () => parseDetailSearch(new URLSearchParams(searchKey)),
    [searchKey],
  );

  // Same key, same options as the list: when the list cached this page (every
  // list here runs `staleTime: Infinity`) this resolves from the cache without a
  // request; on a deep link it fetches once and the list reuses it on the way back.
  const { data, isLoading } = useQuery({
    queryKey: listQueryKey(params),
    queryFn: () => fetchPage(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnReconnect: false,
    retry: 1,
  });

  // A fresh `[]` on every render would rebuild both step callbacks every time.
  const items = useMemo(() => data?.data ?? [], [data]);
  const total = data?.pagination?.total ?? data?.total ?? 0;
  const idx = items.findIndex((row) => row.id === currentId);
  const onPage = idx >= 0;

  // A step in flight disables BOTH chevrons: the page it lands on decides where
  // the ends are, so until it answers neither direction is known to be walkable.
  const stepReady = onPage && !stepping;
  const hasPrevious =
    stepReady && deadEnd !== 'previous' && (idx > 0 || params.pageIndex > 0);
  const hasNext =
    stepReady &&
    deadEnd !== 'next' &&
    (idx < items.length - 1 ||
      (params.pageIndex + 1) * params.pageSize < total);

  // The pager's own prev/next, prefetched as soon as the record they land on
  // is known - within this page, that is immediate (M4 list latency). A step
  // across a page boundary fetches its neighbour first and has no href to
  // prefetch until then, so it is left to the click that already fetches it.
  useEffect(() => {
    if (hasPrevious && idx > 0) {
      prefetchOnce(stepHref(detailPath, items[idx - 1].id, params, hrefFor));
    }
    if (hasNext && idx < items.length - 1) {
      prefetchOnce(stepHref(detailPath, items[idx + 1].id, params, hrefFor));
    }
  }, [hasPrevious, hasNext, idx, items, detailPath, params, hrefFor, prefetchOnce]);

  /** Step to a neighbouring page and land on the row at its near edge. */
  const stepPage = useCallback(
    async (pageIndex: number, edge: 'first' | 'last') => {
      const next = { ...params, pageIndex };
      setStepping(true);
      try {
        const page = await queryClient.fetchQuery({
          queryKey: listQueryKey(next),
          queryFn: () => fetchPage(next),
          staleTime: Infinity,
          gcTime: 1000 * 60 * 60,
        });
        const rows = page?.data ?? [];
        if (!rows.length) {
          setDeadEnd(edge === 'last' ? 'previous' : 'next');
          return;
        }
        const target = edge === 'first' ? rows[0] : rows[rows.length - 1];
        router.push(stepHref(detailPath, target.id, next, hrefFor));
      } finally {
        setStepping(false);
      }
    },
    [detailPath, fetchPage, hrefFor, listQueryKey, params, queryClient, router],
  );

  const goPrevious = useCallback(() => {
    if (!hasPrevious) return;
    if (idx > 0) {
      router.push(stepHref(detailPath, items[idx - 1].id, params, hrefFor));
      return;
    }
    void stepPage(params.pageIndex - 1, 'last');
  }, [detailPath, hasPrevious, hrefFor, idx, items, params, router, stepPage]);

  const goNext = useCallback(() => {
    if (!hasNext) return;
    if (idx < items.length - 1) {
      router.push(stepHref(detailPath, items[idx + 1].id, params, hrefFor));
      return;
    }
    void stepPage(params.pageIndex + 1, 'first');
  }, [detailPath, hasNext, hrefFor, idx, items, params, router, stepPage]);

  return {
    // While the first fetch is in flight nothing is known yet, but hiding the
    // pager and bringing it back would make the header jump; it stays visible and
    // disabled, and only a resolved page that does not hold the record hides it.
    visible: isLoading || onPage,
    index: onPage ? idx + 1 : null,
    total: items.length,
    hasPrevious,
    hasNext,
    goPrevious,
    goNext,
    isLoading: isLoading || stepping,
  };
}
