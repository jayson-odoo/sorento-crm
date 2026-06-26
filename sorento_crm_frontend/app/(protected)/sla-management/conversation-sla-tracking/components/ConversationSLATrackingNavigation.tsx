'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useConversationSLATrackingNeighbours } from '../hooks/useConversationSLATracking';

interface ConversationSLATrackingNavigationProps {
  trackingId: string;
  className?: string;
}

export default function ConversationSLATrackingNavigation({
  trackingId,
  className,
}: ConversationSLATrackingNavigationProps) {
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
      assigned_to: parsed.filters.assigned_to,
      policy_id: parsed.filters.policy_id,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } =
    useConversationSLATrackingNeighbours(trackingId, listParams);

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/sla-management/conversation-sla-tracking/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/sla-management/conversation-sla-tracking"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="conversation SLA tracking"
      className={className}
    />
  );
}
