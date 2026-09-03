'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  approveBoardTransfer,
  approveBoardTransfers,
  listBoardTransfers,
} from '../services/boardTransfersService';
import { STOCK_TRANSFERS_KEY } from '@/app/(protected)/inventory-management/stock-transfers/hooks/useStockTransfers';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export const BOARD_TRANSFERS_KEY = 'board-stock-transfers';

/**
 * The open stock transfers for the orders on this board.
 *
 * Keyed on the SORTED numbers so two boards naming the same orders in a different order
 * share one cache entry rather than fetching the same list twice.
 *
 * `enabled` carries the caller's `inventory.stock_transfers.view` grant (D9): a user who may
 * not read the transfers is not shown them, and must not be made to ask for them either.
 */
export function useBoardTransfers(soNumbers: string[], enabled = true) {
  const key = [...soNumbers].sort();
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [BOARD_TRANSFERS_KEY, key],
    queryFn: () => listBoardTransfers(key),
    enabled: enabled && key.length > 0,
  });
}

/**
 * Approve one, or approve every proposed row.
 *
 * Both invalidate the stock-transfers list as well as this one: the transfers page carries
 * the same rows behind a state filter, and a page still reading "Proposed" beside a movement
 * somebody just approved is how one gets keyed into AutoCount twice.
 */
export function useBoardTransferMutations() {
  const queryClient = useQueryClient();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: [BOARD_TRANSFERS_KEY] });
    void queryClient.invalidateQueries({ queryKey: [STOCK_TRANSFERS_KEY] });
  };

  const approve = useMutation({
    mutationFn: (id: string) => approveBoardTransfer(id),
    onSuccess: (transfer) => {
      invalidate();
      toast.success(`${transfer.transfer_no} approved`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const approveAll = useMutation({
    mutationFn: (ids: string[]) => approveBoardTransfers(ids),
    onSuccess: (result) => {
      invalidate();
      // A bulk verb that silently does less than it was asked reads as a broken button.
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

  return { approve, approveAll };
}
