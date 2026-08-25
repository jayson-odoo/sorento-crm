'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useSalesAgents } from '../hooks/useSalesAgents';

/**
 * Prev/next over the sales-agent list, the twin of `SalesOrderNavigation`.
 *
 * The neighbours come from the SAME searched, sorted list the user was looking at,
 * reconstructed from the query the list carried into the detail URL - classifying 38
 * unclassified codes one after another is exactly the case this exists for, and paging
 * against a default query would step to whatever row happens to be next in an order nobody
 * chose.
 *
 * The walk is the CURRENT PAGE and it stops at both ends: the page is the set the reader
 * picked, so the counter says where they are within it rather than promising a walk through
 * the whole master one chevron at a time.
 */
export default function SalesAgentNavigation({
  salesAgentId,
  className,
}: {
  salesAgentId: string;
  className?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams.toString()));
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
    };
  }, [searchParams]);

  const { data } = useSalesAgents(listParams);

  const items = useMemo(() => (data?.data ?? []).map((a) => ({ id: a.id })), [data]);

  // The list query rides along, unchanged - `page` included, because the walk never leaves it.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/master-data-management/sales-agents/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/master-data-management/sales-agents"
      currentId={salesAgentId}
      items={items}
      // No wrap: the last row on the page is the last row, and a chevron that jumps back to
      // the top without saying so reads as a broken step rather than as a feature.
      circular={false}
      onSelect={handleSelect}
      ariaLabel="sales agent"
      className={className}
    />
  );
}
