'use client';

/**
 * The GRN action set (D15): change status, then Delete.
 *
 * The status changes were a detail-only gear; the list row now offers the same
 * items in the same order, with Delete last and in red.
 */

import { useState } from 'react';
import { Check, Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useUpdateGRN } from './hooks/useGRN';
import type { GRN } from './types/grn.types';
import GRNDeleteDialog from './components/grn-delete-dialog';

/** The three states a GRN moves between. */
const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
] as const;

export interface UseGrnActionsOptions {
  onDeleted?: () => void;
}

export function useGrnActions(
  grn: GRN | undefined | null,
  { onDeleted }: UseGrnActionsOptions = {},
): RecordActionSet {
  const updateMutation = useUpdateGRN();
  const canEdit = useHasPermission('procurement.grn.edit');
  const canDelete = useHasPermission('procurement.grn.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!grn) return { actions, dialogs: null };

  if (canEdit) {
    for (const option of STATUS_OPTIONS) {
      if (option.value === grn.picking_status) continue;
      actions.push({
        key: `grn.set_status:${option.value}`,
        label: `Mark as ${option.label}`,
        icon: Check,
        disabled: updateMutation.isPending,
        run: () => {
          updateMutation.mutate({
            id: grn.id,
            data: { picking_status: option.value },
          });
        },
      });
    }
  }

  if (canDelete) {
    actions.push({
      key: 'grn.delete',
      label: 'Delete GRN',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <GRNDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      grn={grn}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function GrnRowActions({ grn }: { grn: GRN }) {
  const { actions, dialogs } = useGrnActions(grn);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="GRN" />
      {dialogs}
    </>
  );
}
