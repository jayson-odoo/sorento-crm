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
 * "Auto-link" (AC-I1; the captain, 20 Aug: "we need to link already at first already
 * instead of suggesting and needing the users to click 1 by 1"). Runs the cascade over
 * the whole worklist now, rather than waiting for the moments it already runs
 * automatically (a decision confirm, an outstanding PO import, a PO confirm). Confirmed
 * like any bulk write: it links real document lines and writes the audit claim behind
 * each one, even though nothing is deleted and Unlink always reverses it.
 */
export function AutoLinkOrderInquiryDialog({
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
          <AlertDialogTitle>Auto-link</AlertDialogTitle>
          <AlertDialogDescription>
            Link raised order rows to outstanding documents, nearest location and earliest
            purchase order first?
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
            Auto-link
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
