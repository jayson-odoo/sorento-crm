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
import { useBulkDeletePackingLists } from '../hooks/usePackingLists';

interface PackingListBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  packingListIds: string[];
  onSuccess?: () => void;
}

export default function PackingListBulkDeleteDialog({
  open,
  onOpenChange,
  packingListIds,
  onSuccess,
}: PackingListBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeletePackingLists();

  const handleDelete = () => {
    if (packingListIds.length === 0) return;
    bulkDeleteMutation.mutate(packingListIds, {
      onSuccess: () => {
        onOpenChange(false);
        onSuccess?.();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete packing lists</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {packingListIds.length} packing list
          {packingListIds.length !== 1 ? 's' : ''} and their lines? This action cannot be undone.
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
              <LoaderCircleIcon className="animate-spin mr-2 size-4" />
            )}
            Delete {packingListIds.length} packing list
            {packingListIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
