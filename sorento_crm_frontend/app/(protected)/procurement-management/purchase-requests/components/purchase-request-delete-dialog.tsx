'use client';

import { useState } from 'react';
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
import { useDeletePurchaseRequest } from '../hooks/usePurchaseRequests';
import type { PurchaseRequest } from '../types/purchaseRequest.types';

interface PurchaseRequestDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  request: PurchaseRequest;
  /** Label for the entity type in the title (e.g. "Purchase Request", "Sponsorship Form"). */
  entityLabel?: string;
  onSuccess?: () => void;
}

export default function PurchaseRequestDeleteDialog({
  open,
  closeDialog,
  request,
  entityLabel = 'Purchase Request',
  onSuccess,
}: PurchaseRequestDeleteDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const deleteRequest = useDeletePurchaseRequest();

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteRequest.mutateAsync(request.id);
      closeDialog();
      onSuccess?.();
    } catch {
      // Error handled by mutation
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={closeDialog}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {entityLabel}</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete this record? This action cannot be
            undone.
            {(request.customer_name || request.project_title) && (
              <span className="mt-2 block">
                <strong>
                  {request.customer_name || request.project_title}
                </strong>
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
            {isDeleting ? 'Deleting...' : 'Delete'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
