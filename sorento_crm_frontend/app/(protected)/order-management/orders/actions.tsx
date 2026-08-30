'use client';

/**
 * The Delivery Orders action set (D15): set status, then Delete.
 *
 * The status changes used to be a gear on the detail page only; the list row now
 * offers the same items in the same order, and Delete is last, in red.
 */

import { useState } from 'react';
import { CheckCircle2, Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useUpdateOrder } from './hooks/useOrders';
import { useOrderStatusSelectQuery } from '../shared/hooks/use-order-status-select-query';
import type { Order } from './types/order.types';
import OrderDeleteDialog from './components/order-delete-dialog';

export interface UseOrderActionsOptions {
  /** Where to go once the record is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useOrderActions(
  order: Order | undefined | null,
  { onDeleted }: UseOrderActionsOptions = {},
): RecordActionSet {
  const updateMutation = useUpdateOrder();
  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();
  const canEdit = useHasPermission('order_management.orders.edit');
  const canDelete = useHasPermission('order_management.orders.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!order) return { actions, dialogs: null };

  // The two statuses a delivery order actually moves between; everything else
  // is reference data the list filters by.
  const statusList = orderStatuses ?? [];
  const newOrDelivered = statusList.filter((s) => {
    const code = (s.status_code ?? '').toString().trim().toLowerCase();
    return code === 'new' || code === 'delivered';
  });
  const selectable = newOrDelivered.length > 0 ? newOrDelivered : statusList;

  if (canEdit) {
    for (const status of selectable) {
      if (status.id === order.order_status_id) continue;
      actions.push({
        key: `order.set_status:${status.id}`,
        label: `Mark as ${status.status_name}`,
        icon: CheckCircle2,
        disabled: updateMutation.isPending,
        run: () => {
          updateMutation.mutate({
            id: order.id,
            data: { order_status_id: status.id },
          });
        },
      });
    }
  }

  if (canDelete) {
    actions.push({
      key: 'order.delete',
      label: 'Delete delivery order',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <OrderDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      order={order}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function OrderRowActions({ order }: { order: Order }) {
  const { actions, dialogs } = useOrderActions(order);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="delivery order" />
      {dialogs}
    </>
  );
}
