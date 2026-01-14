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
import { useDeleteStockInquiry } from '../hooks/useStockInquiries';
import type { StockInquiry } from '../types/stockInquiry.types';

interface StockInquiryDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  inquiry: StockInquiry;
  onSuccess?: () => void;
}

export default function StockInquiryDeleteDialog({
  open,
  closeDialog,
  inquiry,
  onSuccess,
}: StockInquiryDeleteDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const deleteInquiry = useDeleteStockInquiry();

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteInquiry.mutateAsync(inquiry.id);
      closeDialog();
      onSuccess?.();
    } catch (error) {
      // Error is handled by the mutation
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={closeDialog}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Stock Inquiry</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete this stock inquiry? This action
            cannot be undone.
            {inquiry.product_code && (
              <div className="mt-2">
                <strong>Product Code:</strong> {inquiry.product_code}
              </div>
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
