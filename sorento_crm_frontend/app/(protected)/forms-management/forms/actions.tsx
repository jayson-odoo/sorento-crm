'use client';

/**
 * The Forms action set (D15): Delete.
 *
 * Edit is the record page's primary button and the row click opens the record.
 * The confirm dialog lives here, so the list row's "..." opens the same one.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeleteForm } from './hooks/useForms';

/** What the confirm dialog needs to name the record it is about to remove. */
export interface FormActionRecord {
  id: string;
  name: string;
  code: string;
}

export interface UseFormActionsOptions {
  onDeleted?: () => void;
}

export function useFormActions(
  form: FormActionRecord | undefined | null,
  { onDeleted }: UseFormActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('forms.forms.delete');
  const deleteMutation = useDeleteForm();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!form) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'form.delete',
      label: 'Delete form',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete form</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete <strong>{form.name}</strong> ({form.code})?
            This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={deleteMutation.isPending}
            onClick={() =>
              deleteMutation.mutate(form.id, {
                onSuccess: () => {
                  setDeleteOpen(false);
                  onDeleted?.();
                },
              })
            }
          >
            {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function FormRowActions({ form }: { form: FormActionRecord }) {
  const { actions, dialogs } = useFormActions(form);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="form" />
      {dialogs}
    </>
  );
}
