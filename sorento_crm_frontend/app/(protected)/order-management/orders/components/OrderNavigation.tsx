'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useOrderNeighbours } from '../hooks/useOrders';

interface OrderNavigationProps {
  orderId: string;
  className?: string;
}

export default function OrderNavigation({ orderId, className }: OrderNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams.toString()));
    const hol = parsed.filters.has_order_lines;
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      order_status_id: parsed.filters.order_status_id,
      has_order_lines: (hol === 'yes' || hol === 'no' ? hol : 'all') as
        | 'all'
        | 'yes'
        | 'no',
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useOrderNeighbours(
    orderId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/order-management/orders/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/order-management/orders"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="delivery order"
      className={className}
    />
  );
}
