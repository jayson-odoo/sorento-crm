'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useAccessAgentNeighbours } from '../hooks/useAccessAgents';

interface AccessAgentNavigationProps {
  accessAgentId: string;
  className?: string;
}

export default function AccessAgentNavigation({
  accessAgentId,
  className,
}: AccessAgentNavigationProps) {
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

  const { prevId, nextId, index, total, isLoading } = useAccessAgentNeighbours(
    accessAgentId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/user-management/access-agents/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/user-management/access-agents"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="access agent"
      className={className}
    />
  );
}
