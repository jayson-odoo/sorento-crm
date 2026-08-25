'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { usePurchaseOrders } from '../../hooks/usePurchaseOrders';

/**
 * Prev/next over the purchase-order list, the twin of `SalesOrderNavigation`.
 *
 * The neighbours come from the SAME filtered, sorted list the user was looking at,
 * reconstructed from the query the list carried into the detail URL. It used to rebuild only
 * `status` and `supplier` while the list writes `status`, `product_code` and `outstanding` -
 * so the pager walked a DIFFERENT set from the one on screen, and the row after the one you
 * opened was not the row under it in the list.
 *
 * **The walk is the CURRENT PAGE, and it stops at both ends.** It used to count "1 / 13,856"
 * against the whole result set, which read as a promise to walk 13,856 records one chevron
 * at a time. The page is the set the reader chose to look at, so the counter says where they
 * are within it and the chevron greys out at its edge.
 */
export default function PurchaseOrderNavigation({
  purchaseOrderId,
  className,
}: {
  purchaseOrderId: string;
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
      supplier: null,
      productCode: parsed.filters.product_code || null,
      // Three states, not two: the list's All / Outstanding / Completed toggle writes
      // `true`, `false` or nothing at all, and reading a missing param as `false` would
      // silently narrow the walk to the completed orders.
      outstanding: parsed.filters.outstanding
        ? parsed.filters.outstanding === 'true'
        : null,
    };
  }, [searchParams]);

  const { data } = usePurchaseOrders(listParams);
  const items = useMemo(() => (data?.data ?? []).map((po) => ({ id: po.id })), [data]);

  // Keep the list query on the URL as the user steps, or the second hop would lose the set.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/scm/purchase-orders/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/scm/purchase-orders"
      currentId={purchaseOrderId}
      items={items}
      // No wrap: the last row on the page is the last row, and a chevron that jumps back to
      // the top of the page without saying so reads as a broken step, not as a feature.
      circular={false}
      onSelect={handleSelect}
      ariaLabel="purchase order"
      className={className}
    />
  );
}
