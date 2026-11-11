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
import { useDeleteSLAPolicy } from '../hooks/useSLAPolicies';
import type { SLAPolicy } from '../types/slaPolicy.types';

export interface SLAPolicyDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  slaPolicy: SLAPolicy;
  onSuccess?: () => void;
}

const SLAPolicyDeleteDialog = ({
  open,
  closeDialog,
  slaPolicy,
  onSuccess,
}: SLAPolicyDeleteDialogProps) => {
  const deleteMutation = useDeleteSLAPolicy();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(slaPolicy.id);
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
          <AlertDialogTitle>Delete SLA policy?</AlertDialogTitle>
          <AlertDialogDescription>
            SLA policy{' '}
            <strong className="text-foreground">{slaPolicy.name}</strong> (
            {slaPolicy.code}) is deleted for good, along with all its tiers. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Keep SLA policy</AlertDialogCancel>
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
              'Delete SLA policy'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default SLAPolicyDeleteDialog;
