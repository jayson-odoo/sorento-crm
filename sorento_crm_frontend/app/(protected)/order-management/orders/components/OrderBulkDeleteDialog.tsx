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

/**
 * KEPT as a dialog where S6b turned single-record deletes into grace windows (D7).
 *
 * `/pending-actions` holds ONE pending action per record, and the countdown that
 * replaces the dialog is a countdown for one record: it names what is going ("Ergonomic
 * Chair"), it dims that row, and Cancel withdraws that action. A selection of forty rows
 * has none of those - forty toasts, or one toast that can only say "40 things", and a
 * Cancel that would have to withdraw forty actions and report which of them it missed.
 *
 * Selecting rows and then pressing Delete selected is also already a deliberate two-step
 * gesture, which is what the grace window exists to give a one-click action. So bulk keeps
 * the dialog, and the count in its copy, per the CRUD standard.
 */
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
          <DialogTitle>Delete delivery orders</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {orderIds.length} delivery order
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
            Delete {orderIds.length} delivery order
            {orderIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
