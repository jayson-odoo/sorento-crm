'use client';

/**
 * The Delivery Orders action set (D15): set status, then Delete.
 *
 * The status changes used to be a gear on the detail page only; the list row now
 * offers the same items in the same order, and Delete is last, in red.
 *
 * Neither asks (D7). A status change parks for five seconds and a delete for ten,
 * and the countdown stands where the button was - or in a toast, when the action
 * came from a list row. A record holds one parked action at a time, so while one
 * counts down the rest of the menu waits.
 */

import { CheckCircle2, Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useOrderStatusSelectQuery } from '../shared/hooks/use-order-status-select-query';
import type { Order } from './types/order.types';

export interface UseOrderActionsOptions {
  /** Where to go once the record is gone (the record page returns to the list). */
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useOrderActions(
  order: Order | undefined | null,
  { onDeleted, surface = 'inline' }: UseOrderActionsOptions = {},
): RecordActionSet {
  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();
  const canEdit = useHasPermission('order_management.orders.edit');
  const canDelete = useHasPermission('order_management.orders.delete');
  const orderId = order?.id;
  const subject = order?.order_number ?? '';

  const statusChange = useDeferredAction({
    actionKey: 'order.set_status',
    entityType: 'order',
    entityId: orderId,
    verb: 'Updating',
    subject,
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Delivery order updated',
    invalidateKeys: [['orders'], ['order', orderId]],
  });

  const deletion = useDeferredAction({
    actionKey: 'order.delete',
    entityType: 'order',
    entityId: orderId,
    verb: 'Deleting',
    subject,
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Delivery order deleted',
    invalidateKeys: [['orders']],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!order) return { actions, dialogs: null, pending: null };

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
        disabled: statusChange.isPending || statusChange.isBlocked,
        run: () => statusChange.start({ order_status_id: status.id }),
      });
    }
  }

  if (canDelete) {
    actions.push({
      key: 'order.delete',
      label: 'Delete delivery order',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending || deletion.isBlocked,
      run: () => deletion.start(),
    });
  }

  return {
    actions,
    dialogs: null,
    pending: deletion.countdown ?? statusChange.countdown,
  };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function OrderRowActions({ order }: { order: Order }) {
  const { actions } = useOrderActions(order, { surface: 'toast' });

  if (actions.length === 0) return null;

  return <RowActionsMenu actions={actions} ariaLabel="delivery order" />;
}
