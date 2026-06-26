'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useStockInquiryNeighbours } from '../hooks/useStockInquiries';

interface StockInquiryNavigationProps {
  inquiryId: string;
  className?: string;
}

export default function StockInquiryNavigation({
  inquiryId,
  className,
}: StockInquiryNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    const status = parsed.filters.status;
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      statuses: status ? status.split(',').filter(Boolean) : [],
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useStockInquiryNeighbours(
    inquiryId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/procurement-management/stock-inquiries/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/procurement-management/stock-inquiries"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="stock inquiry"
      className={className}
    />
  );
}
