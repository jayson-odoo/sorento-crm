'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useStockTransfers } from '../hooks/useStockTransfers';

/**
 * Prev/next over the transfers list, the twin of `SalesAgentNavigation`.
 *
 * The neighbours come from the SAME searched, sorted list the reader was looking at,
 * reconstructed from the query the list carried into the detail URL: approving forty
 * movements one after another is exactly the case this exists for, and paging against a
 * default query would step to whatever row happens to be next in an order nobody chose.
 *
 * The walk is the CURRENT PAGE and it stops at both ends, so the counter says where the
 * reader is within the set they picked.
 */
export default function StockTransferNavigation({
  transferId,
  className,
}: {
  transferId: string;
  className?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams.toString()));
    return {
      page: parsed.pageIndex + 1,
      limit: parsed.pageSize,
      sort: parsed.sorting?.[0]?.id,
      dir: (parsed.sorting?.[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
      query: parsed.searchQuery || undefined,
    };
  }, [searchParams]);

  const { data } = useStockTransfers(listParams);

  const items = useMemo(() => (data?.data ?? []).map((row) => ({ id: row.id })), [data]);

  // The list query rides along, unchanged - `page` included, because the walk never leaves it.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/inventory-management/stock-transfers/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/inventory-management/stock-transfers"
      currentId={transferId}
      items={items}
      circular={false}
      onSelect={handleSelect}
      ariaLabel="stock transfer"
      className={className}
    />
  );
}
