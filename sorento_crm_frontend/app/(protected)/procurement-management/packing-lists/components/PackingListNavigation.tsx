'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { usePackingListNeighbours } from '../hooks/usePackingLists';

interface PackingListNavigationProps {
  packingListId: string;
  className?: string;
}

export default function PackingListNavigation({
  packingListId,
  className,
}: PackingListNavigationProps) {
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
      supplier_id: parsed.filters.supplier_id,
      shipment_status: parsed.filters.shipment_status,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = usePackingListNeighbours(
    packingListId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/procurement-management/packing-lists/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/procurement-management/packing-lists"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="packing list"
      className={className}
    />
  );
}
