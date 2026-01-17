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
import { useDeleteSLAPolicyTier } from '../hooks/useSLAPolicies';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

export interface SLAPolicyTierDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  policyId: string;
  tier: SLAPolicyTier;
}

const SLAPolicyTierDeleteDialog = ({
  open,
  closeDialog,
  policyId,
  tier,
}: SLAPolicyTierDeleteDialogProps) => {
  const deleteMutation = useDeleteSLAPolicyTier();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync({ policyId, tierId: tier.id });
      closeDialog();
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
            Are you sure you want to delete tier{' '}
            <strong className="text-foreground">{tier.tier_name}</strong> (Level {tier.tier_level})? This action cannot be undone.
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

export default SLAPolicyTierDeleteDialog;
