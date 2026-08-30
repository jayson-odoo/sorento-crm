'use client';

/**
 * The Promotions action set (D15): Delete.
 *
 * Edit is the record page's primary button and the row click opens the record.
 * The confirm dialog lives here rather than inline in the detail, so the list
 * row's "..." opens the very same one.
 */

import { useState } from 'react';
import { LoaderCircleIcon, Trash2 } from 'lucide-react';
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
import { useDeletePromotion } from './hooks/usePromotions';

export interface UsePromotionActionsOptions {
  onDeleted?: () => void;
}

export function usePromotionActions(
  promotionId: string | undefined | null,
  { onDeleted }: UsePromotionActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('marketing.promotions.delete');
  const deleteMutation = useDeletePromotion();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!promotionId) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'promotion.delete',
      label: 'Delete promotion',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const confirmDelete = async () => {
    try {
      await deleteMutation.mutateAsync(promotionId);
      setDeleteOpen(false);
      onDeleted?.();
    } catch {
      // the mutation raises its own toast
    }
  };

  const dialogs = (
    <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Delete</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete this promotion? This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={confirmDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function PromotionRowActions({ promotionId }: { promotionId: string }) {
  const { actions, dialogs } = usePromotionActions(promotionId);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="promotion" />
      {dialogs}
    </>
  );
}
