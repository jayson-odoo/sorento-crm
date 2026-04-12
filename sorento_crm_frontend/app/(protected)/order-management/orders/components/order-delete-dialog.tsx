'use client';

import { useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useDeleteOrder } from '../hooks/useOrders';
import type { Order } from '../types/order.types';

export interface OrderDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  order: Order;
  onSuccess?: () => void;
}

const OrderDeleteDialog = ({
  open,
  closeDialog,
  order,
  onSuccess,
}: OrderDeleteDialogProps) => {
  const deleteMutation = useDeleteOrder();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(order.id);
      closeDialog();
      if (onSuccess) {
        onSuccess();
      }
    } catch (error) {
      // Error is handled by the mutation hook
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={closeDialog}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirm Delete</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete the delivery order{' '}
            <strong className="text-foreground">{order.order_number}</strong>? This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default OrderDeleteDialog;
