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
import { useDeleteCustomer } from '../hooks/useCustomers';
import type { Customer } from '../types/customer.types';

export interface CustomerDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  customer: Customer;
  onSuccess?: () => void;
}

const CustomerDeleteDialog = ({
  open,
  closeDialog,
  customer,
  onSuccess,
}: CustomerDeleteDialogProps) => {
  const deleteMutation = useDeleteCustomer();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(customer.id);
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
            Are you sure you want to delete the customer{' '}
            <strong className="text-foreground">{customer.customer_name}</strong> (
            {customer.customer_code})? This action cannot be undone.
            {customer.orders_count && customer.orders_count > 0 && (
              <span className="block mt-2 text-destructive">
                Warning: This customer has {customer.orders_count} order(s).
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

export default CustomerDeleteDialog;
