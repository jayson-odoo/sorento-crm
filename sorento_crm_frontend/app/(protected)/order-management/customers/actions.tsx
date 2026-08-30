'use client';

/**
 * The Customers action set (D15): Delete.
 *
 * Edit is the record page's primary button and the row click opens the record,
 * so neither belongs in the menu.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import type { Customer } from './types/customer.types';
import CustomerDeleteDialog from './components/customer-delete-dialog';

export interface UseCustomerActionsOptions {
  onDeleted?: () => void;
}

export function useCustomerActions(
  customer: Customer | undefined | null,
  { onDeleted }: UseCustomerActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('order_management.customers.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!customer) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'customer.delete',
      label: 'Delete customer',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <CustomerDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      customer={customer}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function CustomerRowActions({ customer }: { customer: Customer }) {
  const { actions, dialogs } = useCustomerActions(customer);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="customer" />
      {dialogs}
    </>
  );
}
