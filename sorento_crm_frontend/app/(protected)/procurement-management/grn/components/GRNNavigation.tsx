'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useGRNNeighbours } from '../hooks/useGRN';

interface GRNNavigationProps {
  grnId: string;
  className?: string;
}

export default function GRNNavigation({ grnId, className }: GRNNavigationProps) {
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
      picking_status: parsed.filters.picking_status,
      inspection_status: parsed.filters.inspection_status,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useGRNNeighbours(
    grnId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/procurement-management/grn/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/procurement-management/grn"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="GRN"
      className={className}
    />
  );
}
