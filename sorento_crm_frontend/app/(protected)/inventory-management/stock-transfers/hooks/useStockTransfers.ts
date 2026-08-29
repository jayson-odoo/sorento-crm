'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  approveStockTransfer,
  bulkApproveStockTransfers,
  cancelStockTransfer,
  getStockTransfer,
  listStockTransfers,
  markStockTransferMoved,
} from '../services/stockTransferService';
import type { StockTransferListParams } from '../types/stockTransfer.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

export const STOCK_TRANSFERS_KEY = 'stock-transfers';
export const STOCK_TRANSFER_KEY = 'stock-transfer';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function stockTransfersListQueryKey(
  params: StockTransferListParams = {},
): QueryKey {
  return [STOCK_TRANSFERS_KEY, params];
}

/** The list query a detail URL describes, in the shape the panel passes. */
export function stockTransfersListParamsFromUrl(
  params: ListPagerParams,
): StockTransferListParams {
  const filters = params.filters as Partial<StockTransferListParams>;
  return {
    query: params.searchQuery || undefined,
    state: filters.state,
    kind: filters.kind,
    from_warehouse_id: filters.from_warehouse_id,
    to_warehouse_id: filters.to_warehouse_id,
    product_id: filters.product_id,
    sales_order_id: filters.sales_order_id,
    sales_agent_id: filters.sales_agent_id,
    sort: params.sorting?.[0]?.id,
    dir: (params.sorting?.[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
    page: params.pageIndex + 1,
    limit: params.pageSize,
  };
}

/** The pager's two hooks into the transfers list. */
export const stockTransfersPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    stockTransfersListQueryKey(stockTransfersListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listStockTransfers(stockTransfersListParamsFromUrl(params)),
};

export function useStockTransfers(params: StockTransferListParams = {}) {
  return useQuery({
    queryKey: stockTransfersListQueryKey(params),
    queryFn: () => listStockTransfers(params),
    placeholderData: (previous) => previous,
  });
}

export function useStockTransfer(transferId: string | undefined) {
  return useQuery({
    queryKey: [STOCK_TRANSFER_KEY, transferId],
    queryFn: () => getStockTransfer(transferId as string),
    enabled: Boolean(transferId),
  });
}

/**
 * The four deliberate state changes.
 *
 * All of them invalidate the LIST as well as the row: the list carries the state column
 * and the state filter, and a page still showing "Proposed" beside a transfer somebody
 * just approved is how a movement gets keyed into AutoCount twice.
 */
export function useStockTransferMutations(transferId?: string) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [STOCK_TRANSFERS_KEY] });
    if (transferId) {
      queryClient.invalidateQueries({ queryKey: [STOCK_TRANSFER_KEY, transferId] });
    } else {
      queryClient.invalidateQueries({ queryKey: [STOCK_TRANSFER_KEY] });
    }
  };

  const approve = useMutation({
    mutationFn: (id: string) => approveStockTransfer(id),
    onSuccess: (transfer) => {
      invalidate();
      toast.success(`${transfer.transfer_no} approved`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const markMoved = useMutation({
    mutationFn: ({ id, autocountRef }: { id: string; autocountRef: string }) =>
      markStockTransferMoved(id, autocountRef),
    onSuccess: (transfer) => {
      invalidate();
      toast.success(`${transfer.transfer_no} marked moved`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const cancel = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      cancelStockTransfer(id, reason),
    onSuccess: (transfer) => {
      invalidate();
      toast.success(`${transfer.transfer_no} cancelled`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const bulkApprove = useMutation({
    mutationFn: (ids: string[]) => bulkApproveStockTransfers(ids),
    onSuccess: (result) => {
      invalidate();
      // The skipped count is said out loud rather than swallowed: a bulk verb that
      // silently does less than it was asked reads as a broken button.
      if (result.skipped.length > 0) {
        toast.warning(
          `${result.approved} approved, ${result.skipped.length} skipped: ` +
            result.skipped
              .map((row) => `${row.transfer_no ?? 'unknown'} ${row.reason}`)
              .join(' · '),
        );
        return;
      }
      toast.success(
        `${result.approved} transfer${result.approved === 1 ? '' : 's'} approved`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { approve, markMoved, cancel, bulkApprove };
}
