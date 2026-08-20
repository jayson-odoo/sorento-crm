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
import { useOrderInquiryPlacementMutations } from '../hooks/useOrderInquiry';

/**
 * Untag (section G): the row goes back to `raised` and the reorder engine's next
 * suggestion counts it again. Confirmed, per the CRUD standard - it undoes a deliberate
 * evidence-carrying action (the audit claim is deleted on the backend), not a toggle.
 */
export function UnplaceFromPoDialog({
  open,
  onOpenChange,
  rowId,
  poNumber,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rowId: string;
  poNumber?: string | null;
}) {
  const { unplace } = useOrderInquiryPlacementMutations();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Unplace</AlertDialogTitle>
          <AlertDialogDescription>
            {poNumber
              ? `Remove the tag to ${poNumber}? This row goes back to raised, and the next reorder suggestion counts it again.`
              : 'Remove this tag? This row goes back to raised, and the next reorder suggestion counts it again.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={unplace.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              unplace.mutate(rowId, { onSuccess: () => onOpenChange(false) });
            }}
            disabled={unplace.isPending}
          >
            {unplace.isPending && <LoaderCircleIcon className="mr-2 size-4 animate-spin" />}
            Unplace
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
