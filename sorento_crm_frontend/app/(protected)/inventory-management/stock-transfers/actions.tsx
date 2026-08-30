'use client';

/**
 * The Stock Transfers action set (D15): Approve, then Cancel.
 *
 * A transfer's three verbs were worded once already (`StockTransferActionDialogs`)
 * but chosen twice: the record's gear offered Cancel alone while the list row
 * offered Approve and Cancel. One definition now, two renderings.
 *
 * `approve` comes back separately because it is the PRIMARY: on the record it is
 * the one button in the header, and on a list row, which has no primary slot, it
 * is the first item of the menu.
 */

import type { RecordAction } from '@/components/common/recordActions';
import { availableActions, type TransferAction } from './components/StockTransferActions';
import type { StockTransfer } from './types/stockTransfer.types';

export interface StockTransferActionSet {
  /** The record's one call to action, when its state still allows it. */
  approve: RecordAction | null;
  /** Everything else, Cancel last and in red. */
  actions: RecordAction[];
}

export function stockTransferActions(
  transfer: StockTransfer,
  run: (action: TransferAction) => void,
): StockTransferActionSet {
  const can = availableActions(transfer.state);

  return {
    approve: can.approve
      ? {
          key: 'stock_transfer.approve',
          label: 'Approve',
          run: () => run('approve'),
        }
      : null,
    actions: can.cancel
      ? [
          {
            key: 'stock_transfer.cancel',
            label: 'Cancel transfer',
            kind: 'destructive' as const,
            run: () => run('cancel'),
          },
        ]
      : [],
  };
}
