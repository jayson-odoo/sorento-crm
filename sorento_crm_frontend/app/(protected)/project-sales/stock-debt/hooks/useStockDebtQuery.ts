'use client';

import { useQuery } from '@tanstack/react-query';
import { getStockDebtCell, getStockDebtList } from '../services/stockDebtService';
import type { StockDebtListParams } from '../services/stockDebtService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/**
 * The month x product board (AC-S2-6).
 *
 * `keepPreviousData` so paging or flipping the debt toggle does not blank a wide
 * table back to skeletons - the columns would jump and the reader would lose the
 * month they were looking at.
 */
export function useStockDebtQuery(params: StockDebtListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'project-sales',
      'stock-debt',
      'list',
      params.pageIndex,
      params.pageSize,
      params.query,
      params.group,
      params.onlyDebt,
    ],
    queryFn: () => getStockDebtList(params),
    staleTime: 60_000,
    retry: 1,
  });
}

/**
 * One cell's demand and supply (AC-S2-7). Fires only while its lightbox is open:
 * a board is 4,000 rows x 15 columns, so nothing here is fetched up front.
 *
 * `group` is part of the KEY, not just of the request: the same product and month
 * answer differently under `group=BB`, so a shared cache entry would hand the
 * narrowed board the whole book's drill.
 */
export function useStockDebtCellQuery(
  productId: string | null,
  month: string | null,
  group?: string,
) {
  return useQuery({
    queryKey: ['project-sales', 'stock-debt', 'cell', productId, month, group ?? ''],
    queryFn: () => getStockDebtCell(productId as string, month as string, group),
    enabled: Boolean(productId && month),
    staleTime: 60_000,
    retry: 1,
  });
}
