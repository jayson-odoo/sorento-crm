'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useSupplierNeighbours } from '../hooks/useSuppliers';

interface SupplierNavigationProps {
  supplierId: string;
  className?: string;
}

export default function SupplierNavigation({
  supplierId,
  className,
}: SupplierNavigationProps) {
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

  const { prevId, nextId, index, total, isLoading } = useSupplierNeighbours(
    supplierId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/procurement-management/suppliers/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/procurement-management/suppliers"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="supplier"
      className={className}
    />
  );
}
