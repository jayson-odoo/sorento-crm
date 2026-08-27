'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useStockTransfers } from '../hooks/useStockTransfers';
import type { StockTransferListParams } from '../types/stockTransfer.types';

/**
 * Prev/next over the transfers list, the twin of `SalesAgentNavigation`.
 *
 * The neighbours come from the SAME searched, sorted AND FILTERED list the reader was
 * looking at, reconstructed from the query the list carried into the detail URL
 * (`buildDetailSearch`, which the panel calls with its filters as well as its page and
 * sort). Approving forty movements one after another is exactly the case this exists for,
 * and a pager rebuilt from page and sort alone would step out of the set the reader
 * narrowed to and into the unfiltered book.
 *
 * `parseDetailSearch` returns the unknown params in `filters`, which is where the state /
 * kind / warehouse / product / order / agent keys arrive; they are handed back to the list
 * query under the same names the list GET uses.
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

  const listParams = useMemo<StockTransferListParams>(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams.toString()));
    const filters = parsed.filters as Partial<StockTransferListParams>;
    return {
      page: parsed.pageIndex + 1,
      limit: parsed.pageSize,
      sort: parsed.sorting?.[0]?.id,
      dir: (parsed.sorting?.[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
      query: parsed.searchQuery || undefined,
      state: filters.state,
      kind: filters.kind,
      from_warehouse_id: filters.from_warehouse_id,
      to_warehouse_id: filters.to_warehouse_id,
      product_id: filters.product_id,
      sales_order_id: filters.sales_order_id,
      sales_agent_id: filters.sales_agent_id,
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
