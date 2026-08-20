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
import { useAutoPlaceOrderInquiryRows } from '../hooks/useOrderInquiry';

/**
 * "Auto-place" (G2 rule 4, the captain, 20 Aug: "we need to link already at first
 * already instead of suggesting and needing the users to click 1 by 1"). Runs the
 * cascade over the whole worklist now, rather than waiting for the three moments it
 * already runs automatically (an outstanding PO import, a decision confirm, or the next
 * scheduled pass). Confirmed like any bulk write: it tags real purchase-order lines and
 * writes the audit claim behind each one, even though nothing is deleted and Unplace
 * always reverses it.
 */
export function AutoPlaceOrderInquiryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const autoPlace = useAutoPlaceOrderInquiryRows();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Auto-place</AlertDialogTitle>
          <AlertDialogDescription>
            Automatically tag raised order rows to outstanding PO lines, earliest first?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={autoPlace.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              autoPlace.mutate({}, { onSuccess: () => onOpenChange(false) });
            }}
            disabled={autoPlace.isPending}
          >
            {autoPlace.isPending && <LoaderCircleIcon className="mr-2 size-4 animate-spin" />}
            Auto-place
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
