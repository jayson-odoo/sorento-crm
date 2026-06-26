'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useCustomerNeighbours } from '../hooks/useCustomers';

interface CustomerNavigationProps {
  customerId: string;
  className?: string;
}

export default function CustomerNavigation({
  customerId,
  className,
}: CustomerNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useCustomerNeighbours(
    customerId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/order-management/customers/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/order-management/customers"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="customer"
      className={className}
    />
  );
}
