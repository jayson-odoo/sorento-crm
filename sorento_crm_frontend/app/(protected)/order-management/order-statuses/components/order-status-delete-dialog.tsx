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
import { useDeleteOrderStatus } from '../hooks/useOrderStatuses';
import type { OrderStatus } from '../types/orderStatus.types';

export interface OrderStatusDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  orderStatus: OrderStatus;
  onSuccess?: () => void;
}

const OrderStatusDeleteDialog = ({
  open,
  closeDialog,
  orderStatus,
  onSuccess,
}: OrderStatusDeleteDialogProps) => {
  const deleteMutation = useDeleteOrderStatus();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(orderStatus.id);
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
            Are you sure you want to delete the order status{' '}
            <strong className="text-foreground">{orderStatus.status_name}</strong> (
            {orderStatus.status_code})? This action cannot be undone.
            {orderStatus.orders_count && orderStatus.orders_count > 0 && (
              <span className="block mt-2 text-destructive">
                Warning: This status is currently used by {orderStatus.orders_count} order(s).
              </span>
            )}
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

export default OrderStatusDeleteDialog;
