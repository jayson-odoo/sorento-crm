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
import { useDeleteComplaint } from '../hooks/useComplaints';
import type { Complaint } from '../types/complaint.types';

interface ComplaintDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  complaint: Complaint;
  onSuccess?: () => void;
}

export default function ComplaintDeleteDialog({
  open,
  closeDialog,
  complaint,
  onSuccess,
}: ComplaintDeleteDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const deleteComplaint = useDeleteComplaint();

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteComplaint.mutateAsync(complaint.id);
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
          <AlertDialogTitle>Delete complaint?</AlertDialogTitle>
          <AlertDialogDescription>
            The complaint is deleted for good. This cannot be undone.
            {complaint.delivery_order_number && (
              <div className="mt-2">
                <strong>DO Number:</strong> {complaint.delivery_order_number}
              </div>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Keep complaint</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? 'Deleting...' : 'Delete complaint'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
