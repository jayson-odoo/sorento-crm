'use client';

/**
 * The Suppliers action set (D15): Delete.
 *
 * Edit is the record page's primary button and the row click opens the record.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import type { Supplier } from './types/supplier.types';
import SupplierDeleteDialog from './components/supplier-delete-dialog';

export interface UseSupplierActionsOptions {
  onDeleted?: () => void;
}

export function useSupplierActions(
  supplier: Supplier | undefined | null,
  { onDeleted }: UseSupplierActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('procurement.suppliers.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!supplier) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'supplier.delete',
      label: 'Delete supplier',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <SupplierDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      supplier={supplier}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function SupplierRowActions({ supplier }: { supplier: Supplier }) {
  const { actions, dialogs } = useSupplierActions(supplier);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="supplier" />
      {dialogs}
    </>
  );
}
