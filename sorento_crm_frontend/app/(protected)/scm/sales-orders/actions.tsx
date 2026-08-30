'use client';

/**
 * The Sales Order action set (D15).
 *
 * Delete was a red icon button in the list's actions column and did not exist on
 * the record page at all, so the only way to remove a sales order was to find it
 * again in the list. One array now, rendered by the row's "..." and the record's
 * gear.
 *
 * Edit is not here: it is the record's primary button, and on the list the row
 * click opens the record.
 */

import { Trash2 } from 'lucide-react';

import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';

/** What both surfaces hand over: a list row carries exactly this much. */
export interface SalesOrderActionTarget {
  id: string;
  so_number?: string | null;
  customer_name?: string | null;
}

export interface UseSalesOrderActionsOptions {
  /** Where to go once the order is gone (the record page returns to the list). */
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useSalesOrderActions(
  order: SalesOrderActionTarget | null | undefined,
  { onDeleted, surface = 'inline' }: UseSalesOrderActionsOptions = {},
): RecordActionSet {
  // Delete asks nothing (D7): the countdown takes the record's primary slot, or
  // the toast on a list row, and Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'scm_sales_order.delete',
    entityType: 'scm_sales_order',
    entityId: order?.id,
    verb: 'Deleting',
    subject: order
      ? `${order.so_number ?? 'this order'}${order.customer_name ? ` for ${order.customer_name}` : ''}`
      : '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Sales order deleted.',
    invalidateKeys: [['scm', 'sales-orders']],
    onCommitted: onDeleted,
  });

  if (!order) return { actions: [], dialogs: null, pending: null };

  const actions: RecordAction[] = [
    {
      key: 'sales_order.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    },
  ];

  return { actions, dialogs: null, pending: deletion.countdown };
}
