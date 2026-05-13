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
import { useBulkDeleteWarehouses } from '../hooks/useWarehouses';

interface WarehouseBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  warehouseIds: string[];
  onSuccess?: () => void;
}

export default function WarehouseBulkDeleteDialog({
  open,
  onOpenChange,
  warehouseIds,
  onSuccess,
}: WarehouseBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteWarehouses();

  const handleDelete = () => {
    if (warehouseIds.length === 0) return;
    bulkDeleteMutation.mutate(warehouseIds, {
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
          <DialogTitle>Confirm delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {warehouseIds.length} warehouse
          {warehouseIds.length !== 1 ? 's' : ''}? Rows with linked stock, zones, or allocations
          will be skipped and reported. This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={handleDelete}
            disabled={bulkDeleteMutation.isPending}
          >
            {bulkDeleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2 size-4" />
            )}
            Delete {warehouseIds.length} warehouse
            {warehouseIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
