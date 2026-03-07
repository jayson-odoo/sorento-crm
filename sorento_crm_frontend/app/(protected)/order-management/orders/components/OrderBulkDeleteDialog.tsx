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
import { useBulkDeleteOrders } from '../hooks/useOrders';

interface OrderBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderIds: string[];
  onSuccess?: () => void;
}

export default function OrderBulkDeleteDialog({
  open,
  onOpenChange,
  orderIds,
  onSuccess,
}: OrderBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteOrders();

  const handleDelete = () => {
    if (orderIds.length === 0) return;
    bulkDeleteMutation.mutate(orderIds, {
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
          <DialogTitle>Delete orders</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {orderIds.length} order
          {orderIds.length !== 1 ? 's' : ''}? This action cannot be undone.
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
            Delete {orderIds.length} order
            {orderIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
