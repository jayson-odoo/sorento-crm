'use client';

/**
 * Prev/next through the review queue, walking the exact filtered+sorted set the
 * reviewer navigated from (carried in the detail URL by `buildDetailSearch`).
 */

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useOnboardingRequestNeighbours } from '../../hooks/useOnboardingRequests';

const BASE_PATH = '/user-management/onboarding-requests';

export function OnboardingRequestNavigation({ requestId }: { requestId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams?.toString() ?? ''));
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      statusKey: parsed.filters.status_key,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useOnboardingRequestNeighbours(
    requestId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams?.toString() ?? '';
    router.push(`${BASE_PATH}/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath={BASE_PATH}
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="onboarding request"
    />
  );
}
