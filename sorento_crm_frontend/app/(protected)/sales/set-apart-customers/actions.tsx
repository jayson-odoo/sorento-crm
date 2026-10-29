'use client';

/**
 * The set-apart row actions: Edit, then Delete. Delete asks nothing (D7): it parks
 * `sales_set_apart.delete` on the server for the hard-delete window and a toast over the
 * list carries the countdown and Cancel.
 */

import { Pencil, Trash2 } from 'lucide-react';
import type { RecordAction } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { SET_APART_KEY } from './hooks/useSetApart';
import type { SetApartRow } from './types/setApart.types';

export function SetApartRowActions({ row, onEdit }: { row: SetApartRow; onEdit: (row: SetApartRow) => void }) {
  const canEdit = useHasPermission('sales.set_apart.edit');

  const deletion = useDeferredAction({
    actionKey: 'sales_set_apart.delete',
    entityType: 'sales_set_apart',
    entityId: row.id,
    verb: 'Deleting',
    subject: row.customer_name ?? row.debtor_code ?? '',
    surface: 'toast',
    successMessage: 'Set-apart customer deleted',
    invalidateKeys: [SET_APART_KEY],
  });

  if (!canEdit) return null;

  const actions: RecordAction[] = [
    { key: 'sales_set_apart.edit', label: 'Edit', icon: Pencil, run: () => onEdit(row) },
    {
      key: 'sales_set_apart.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    },
  ];
  return <RowActionsMenu actions={actions} ariaLabel="set-apart customer" />;
}
