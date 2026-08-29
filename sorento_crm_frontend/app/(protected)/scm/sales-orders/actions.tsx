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

import { useState } from 'react';
import { Trash2 } from 'lucide-react';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { useDeleteSalesOrder } from '../hooks/useSalesOrders';

/** What both surfaces hand over: a list row carries exactly this much. */
export interface SalesOrderActionTarget {
  id: string;
  so_number?: string | null;
  customer_name?: string | null;
}

export interface UseSalesOrderActionsOptions {
  /** Where to go once the order is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useSalesOrderActions(
  order: SalesOrderActionTarget | null | undefined,
  { onDeleted }: UseSalesOrderActionsOptions = {},
): RecordActionSet {
  const remove = useDeleteSalesOrder();
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (!order) return { actions: [] };

  const actions: RecordAction[] = [
    {
      key: 'sales_order.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: remove.isPending,
      run: () => setDeleteOpen(true),
    },
  ];

  const dialogs = (
    <ConfirmDeleteDialog
      open={deleteOpen}
      onOpenChange={setDeleteOpen}
      description={
        <>
          Delete sales order <span className="font-medium">{order.so_number}</span>
          {order.customer_name ? ` for ${order.customer_name}` : ''}? This action cannot be
          undone.
        </>
      }
      successMessage="Sales order deleted."
      onDelete={async () => {
        await remove.mutateAsync(order.id);
      }}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}
