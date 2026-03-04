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
import { useBulkDeleteGRNs } from '../hooks/useGRN';

interface GRNBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  grnIds: string[];
  onSuccess?: () => void;
}

export default function GRNBulkDeleteDialog({
  open,
  onOpenChange,
  grnIds,
  onSuccess,
}: GRNBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteGRNs();

  const handleDelete = () => {
    if (grnIds.length === 0) return;
    bulkDeleteMutation.mutate(grnIds, {
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
          <DialogTitle>Delete GRNs</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {grnIds.length} GRN
          {grnIds.length !== 1 ? 's' : ''} and their lines? This action cannot be undone.
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
            Delete {grnIds.length} GRN
            {grnIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
