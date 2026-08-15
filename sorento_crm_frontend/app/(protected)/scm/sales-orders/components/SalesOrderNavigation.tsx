'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useSalesOrders } from '../../hooks/useSalesOrders';

/**
 * Prev/next over the sales-order list, the twin of `PurchaseOrderNavigation`.
 *
 * The neighbours come from the SAME filtered, sorted list the user was looking at,
 * reconstructed from the query the list carried into the detail URL. Paging against a default
 * query instead would step to whatever row happens to be next in an order the user never
 * chose, which is worse than having no pager: reviewing 11,000 absorbed orders one by one is
 * exactly the case this exists for.
 *
 * **It steps across page boundaries.** The counter says "1 / 11,626", and a pager that could
 * only reach the 25 rows the list happened to have loaded made that counter a lie: the reader
 * is told there are 11,626 records and then cannot get to the 26th. So the window is the
 * current page plus one row either side of it, taken from the neighbouring pages, and
 * stepping onto one of those rows rewrites `page` in the URL so the next step continues from
 * there rather than snapping back.
 *
 * Two extra pages of 25 rows is the cost, on a query react-query has usually cached already
 * because the list itself asked for the same page a moment ago.
 */
export default function SalesOrderNavigation({
  salesOrderId,
  className,
}: {
  salesOrderId: string;
  className?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams.toString()));
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      status: parsed.filters.status || null,
      priority: parsed.filters.priority || null,
      source: parsed.filters.source || null,
      dateFrom: parsed.filters.date_from || null,
      dateTo: parsed.filters.date_to || null,
      customerId: parsed.filters.customer_code || null,
      outstanding: parsed.filters.outstanding === 'true',
    };
  }, [searchParams]);

  const { data } = useSalesOrders(listParams);
  const isFirstPage = listParams.pageIndex === 0;
  const previousPage = useSalesOrders({
    ...listParams,
    pageIndex: Math.max(listParams.pageIndex - 1, 0),
  });
  const nextPage = useSalesOrders({ ...listParams, pageIndex: listParams.pageIndex + 1 });

  const total = data?.pagination.total ?? 0;
  const pageRows = useMemo(() => data?.data ?? [], [data]);

  /**
   * The current page, with one borrowed row at each end so a step off either edge has
   * somewhere to go. The borrowed rows carry the page they came from, which is what keeps the
   * URL honest as the user walks past a boundary.
   */
  const window = useMemo(() => {
    const rows: { id: string; page: number }[] = pageRows.map((so) => ({
      id: so.id,
      page: listParams.pageIndex,
    }));
    if (!isFirstPage) {
      const before = previousPage.data?.data ?? [];
      const last = before[before.length - 1];
      if (last) rows.unshift({ id: last.id, page: listParams.pageIndex - 1 });
    }
    const after = nextPage.data?.data ?? [];
    if (after[0]) rows.push({ id: after[0].id, page: listParams.pageIndex + 1 });
    return rows;
  }, [pageRows, previousPage.data, nextPage.data, listParams.pageIndex, isFirstPage]);

  const items = useMemo(() => window.map((r) => ({ id: r.id })), [window]);

  // The offset counts from the first row of the current page, adjusted for a borrowed row in
  // front of it, so the counter reads the record's position in the WHOLE list.
  const borrowedBefore = window.length && window[0].page < listParams.pageIndex ? 1 : 0;
  const pageItemOffset = listParams.pageIndex * listParams.pageSize - borrowedBefore;

  const handleSelect = (id: string) => {
    const params = new URLSearchParams(searchParams.toString());
    const target = window.find((r) => r.id === id);
    // Rewrite the page as the user crosses a boundary. Without this the next step would be
    // computed against the page they came FROM and walk backwards into it.
    if (target) params.set('page', String(target.page + 1));
    const qs = params.toString();
    router.push(`/scm/sales-orders/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/scm/sales-orders"
      currentId={salesOrderId}
      items={items}
      totalCount={total}
      pageItemOffset={Math.max(pageItemOffset, 0)}
      onSelect={handleSelect}
      ariaLabel="sales order"
      className={className}
    />
  );
}
