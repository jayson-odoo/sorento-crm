'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useSalesOrders } from '../../hooks/useSalesOrders';

/**
 * Prev/next over the sales-order list, the twin of `PurchaseOrderNavigation`.
 *
 * The neighbours come from the SAME page of the SAME filtered, sorted list the user was
 * looking at, reconstructed from the query the list carried into the detail URL. Paging
 * against a default query instead would step to whatever row happens to be next in an order
 * the user never chose, which is worse than having no pager: reviewing 11,000 absorbed
 * orders one by one is exactly the case this exists for.
 *
 * Neighbours are drawn from the loaded page rather than a dedicated endpoint, so the pager
 * walks within the page and the counter says where in the whole list that page sits.
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
    };
  }, [searchParams]);

  const { data } = useSalesOrders(listParams);
  const items = useMemo(() => (data?.data ?? []).map((so) => ({ id: so.id })), [data]);

  // Keep the list query on the URL as the user steps, or the second hop would lose the set.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/scm/sales-orders/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/scm/sales-orders"
      currentId={salesOrderId}
      items={items}
      totalCount={data?.pagination.total}
      pageItemOffset={listParams.pageIndex * listParams.pageSize}
      onSelect={handleSelect}
      ariaLabel="sales order"
      className={className}
    />
  );
}
