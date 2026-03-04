'use client';

import { LoaderCircleIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useBulkDeletePurchaseRequests } from '../hooks/usePurchaseRequests';

interface PurchaseRequestBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ids: string[];
  /** e.g. "Purchase Request", "Sponsorship Form", or "record" when mixed. */
  entityLabel?: string;
  onSuccess?: () => void;
}

export default function PurchaseRequestBulkDeleteDialog({
  open,
  onOpenChange,
  ids,
  entityLabel = 'record',
  onSuccess,
}: PurchaseRequestBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeletePurchaseRequests();

  const handleDelete = () => {
    if (ids.length === 0) return;
    bulkDeleteMutation.mutate(ids, {
      onSuccess: () => {
        onOpenChange(false);
        onSuccess?.();
      },
    });
  };

  const noun = ids.length === 1 ? entityLabel : `${entityLabel}s`;
  const title =
    entityLabel === 'record'
      ? `Delete ${ids.length} record${ids.length !== 1 ? 's' : ''}`
      : `Delete ${ids.length} ${noun}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {ids.length} {noun}? This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={bulkDeleteMutation.isPending}
          >
            {bulkDeleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2" />
            )}
            Delete {ids.length} {noun}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
