'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

export const STOCK_TRANSFERS_KEY = 'stock-transfers';
export const STOCK_TRANSFER_KEY = 'stock-transfer';

export function useStockTransfers(params: StockTransferListParams = {}) {
  return useQuery({
    queryKey: [STOCK_TRANSFERS_KEY, params],
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
