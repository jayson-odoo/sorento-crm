'use client';

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
import { useBulkDeletePromotions } from '../hooks/usePromotions';

interface PromotionBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promotionIds: string[];
  onSuccess?: () => void;
}

export default function PromotionBulkDeleteDialog({
  open,
  onOpenChange,
  promotionIds,
  onSuccess,
}: PromotionBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeletePromotions();

  const handleDelete = () => {
    if (promotionIds.length === 0) return;
    bulkDeleteMutation.mutate(promotionIds, {
      onSuccess: () => {
        onOpenChange(false);
        onSuccess?.();
      },
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirm delete</AlertDialogTitle>
          <AlertDialogDescription>
            Permanently delete {promotionIds.length} promotion
            {promotionIds.length !== 1 ? 's' : ''}? This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={bulkDeleteMutation.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleDelete();
            }}
            disabled={bulkDeleteMutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {bulkDeleteMutation.isPending && (
              <LoaderCircleIcon className="size-4 animate-spin mr-2" />
            )}
            Delete {promotionIds.length} promotion
            {promotionIds.length !== 1 ? 's' : ''}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
