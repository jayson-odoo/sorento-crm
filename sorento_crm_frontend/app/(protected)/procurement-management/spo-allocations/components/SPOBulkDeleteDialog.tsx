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
import { useBulkDeleteSPOAllocations } from '../hooks/useSPOAllocations';

interface SPOBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allocationIds: string[];
  onSuccess?: () => void;
}

export default function SPOBulkDeleteDialog({
  open,
  onOpenChange,
  allocationIds,
  onSuccess,
}: SPOBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteSPOAllocations();

  const handleDelete = () => {
    if (allocationIds.length === 0) return;
    bulkDeleteMutation.mutate(allocationIds, {
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
          <DialogTitle>Delete SPO allocations</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {allocationIds.length} SPO allocation
          {allocationIds.length !== 1 ? 's' : ''}? This action cannot be undone.
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
            Delete {allocationIds.length} allocation
            {allocationIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
