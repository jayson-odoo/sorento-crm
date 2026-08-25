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
 * **The walk is the CURRENT PAGE, and it stops at both ends.** It used to borrow a row from
 * each neighbouring page and count "1 / 13,856" against the whole result set, which read as a
 * promise to walk 13,856 records one chevron at a time. The page is the set the reader chose
 * to look at, so the counter says where they are within it and the chevron greys out at its
 * edge rather than quietly rewriting `page` underneath them.
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
      // Both were carried into the detail URL by the list and dropped here, so a walk that
      // began on "SEAN III's project orders" stepped through the unfiltered book instead.
      // The agent one matters twice over now: the sales-agent record's Sales orders tab
      // links every row with `sales_agent_id` set, and that IS the set being walked.
      salesAgentId: parsed.filters.sales_agent_id || null,
      demandClass: parsed.filters.demand_class || null,
    };
  }, [searchParams]);

  const { data } = useSalesOrders(listParams);

  const items = useMemo(() => (data?.data ?? []).map((so) => ({ id: so.id })), [data]);

  // The list query rides along, unchanged - `page` included, because the walk never leaves it.
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
      // No wrap: the last row on the page is the last row, and a chevron that jumps back to
      // the top of the page without saying so reads as a broken step, not as a feature.
      circular={false}
      onSelect={handleSelect}
      ariaLabel="sales order"
      className={className}
    />
  );
}
