'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { usePromotionNeighbours } from '../hooks/usePromotions';
import type { PromotionsListParams } from '../services/promotionService';

interface PromotionNavigationProps {
  promotionId: string;
  className?: string;
}

export default function PromotionNavigation({
  promotionId,
  className,
}: PromotionNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo<PromotionsListParams>(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      status: parsed.filters.status,
      user_type: parsed.filters.user_type,
      attachment_state: parsed.filters
        .attachment_state as PromotionsListParams['attachment_state'],
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = usePromotionNeighbours(
    promotionId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/marketing-management/promotions/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/marketing-management/promotions"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="promotion"
      className={className}
    />
  );
}
