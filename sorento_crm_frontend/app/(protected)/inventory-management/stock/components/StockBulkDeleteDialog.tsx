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
import { useBulkDeleteStock } from '../hooks/useStock';

interface StockBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stockIds: string[];
  onSuccess?: () => void;
}

export default function StockBulkDeleteDialog({
  open,
  onOpenChange,
  stockIds,
  onSuccess,
}: StockBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteStock();

  const handleDelete = () => {
    if (stockIds.length === 0) return;
    bulkDeleteMutation.mutate(stockIds, {
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
          <DialogTitle>Delete stock records</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {stockIds.length} stock record
          {stockIds.length !== 1 ? 's' : ''} (product–warehouse balance)? This action cannot be undone.
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
            Delete {stockIds.length} record
            {stockIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
