'use client';

import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoaderCircleIcon } from 'lucide-react';
import { useBulkDeleteProducts } from '../hooks/useProducts';

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
interface ProductBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productIds: string[];
  onSuccess?: () => void;
}

export default function ProductBulkDeleteDialog({
  open,
  onOpenChange,
  productIds,
  onSuccess,
}: ProductBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteProducts();

  const handleDelete = () => {
    if (productIds.length === 0) return;
    bulkDeleteMutation.mutate(productIds, {
      onSuccess: () => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>
                {productIds.length} product{productIds.length !== 1 ? 's' : ''} deleted successfully
              </AlertTitle>
            </Alert>
          ),
          { position: 'top-center' },
        );
        onOpenChange(false);
        onSuccess?.();
      },
      onError: (error: Error) => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="destructive">
              <AlertIcon>
                <RiErrorWarningFill />
              </AlertIcon>
              <AlertTitle>{error.message || 'Failed to delete products'}</AlertTitle>
            </Alert>
          ),
          { position: 'top-center' },
        );
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Batch Delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete {productIds.length} product
          {productIds.length !== 1 ? 's' : ''}? This action cannot be undone.
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
              <LoaderCircleIcon className="size-4 animate-spin mr-2" />
            )}
            Delete {productIds.length} product{productIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
