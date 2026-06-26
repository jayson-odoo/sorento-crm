'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { usePurchaseRequestNeighbours } from '../hooks/usePurchaseRequests';

interface PurchaseRequestNavigationProps {
  requestId: string;
  /** Base path for the list/detail route (purchase-requests or sponsorship-forms). */
  basePath: string;
  /** aria-label for the pager (e.g. "purchase request", "sponsorship form"). */
  ariaLabel?: string;
  className?: string;
}

export default function PurchaseRequestNavigation({
  requestId,
  basePath,
  ariaLabel = 'record',
  className,
}: PurchaseRequestNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // The two single-type pages (purchase-requests / sponsorship-forms) share this
  // detail. Derive request_type from the base path so navigation NEVER crosses
  // between PRs and SFs, even on a deep link with no carried query.
  const requestTypeForNav = basePath.includes('sponsorship-forms')
    ? 'sponsorship_form'
    : 'purchase_request';

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
      // request_type is forced from the base path so PR nav stays in PRs / SF in SFs.
      request_type: requestTypeForNav,
      approval_status: parsed.filters.approval_status,
      assigned_to: parsed.filters.assigned_to,
    };
  }, [searchParams, requestTypeForNav]);

  const { prevId, nextId, index, total, isLoading } =
    usePurchaseRequestNeighbours(requestId, listParams);

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`${basePath}/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath={basePath}
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel={ariaLabel}
      className={className}
    />
  );
}
