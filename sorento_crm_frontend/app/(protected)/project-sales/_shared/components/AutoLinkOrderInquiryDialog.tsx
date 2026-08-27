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
import { horizonLabel, linkHorizonRequest } from '../lib/linkHorizon';

/**
 * "Auto-link" (AC-I1; the captain, 20 Aug: "we need to link already at first already
 * instead of suggesting and needing the users to click 1 by 1"). Runs the cascade over
 * the whole worklist now, rather than waiting for the moments it already runs
 * automatically (a decision confirm, an outstanding PO import, a PO confirm). Confirmed
 * like any bulk write: it links real document lines and writes the audit claim behind
 * each one, even though nothing is deleted and Unlink always reverses it.
 *
 * It runs under the page's own LINK HORIZON, and SHOWS it (B2, code review 27 Aug 2026).
 * This press sat on the same toolbar as the date and ignored it, so the one press that
 * reaches every open row in the company was also the one that could reach past the date
 * beside it - and nothing on the confirmation said so.
 */
export function AutoLinkOrderInquiryDialog({
  open,
  onOpenChange,
  linkUpTo = '',
  horizonCleared = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The page's "Link up to" date, `YYYY-MM-DD`, or blank. */
  linkUpTo?: string;
  /** The buyer took the horizon off, as opposed to never having set one (S1). */
  horizonCleared?: boolean;
}) {
  const autoPlace = useAutoPlaceOrderInquiryRows();
  const horizon = horizonLabel(linkUpTo, horizonCleared);

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
        {/* The horizon this press runs to, worded exactly as the manual Link dialog words
            it. A fact and a date, never an explanation of what a horizon is. */}
        {horizon ? (
          <div
            data-testid="auto-link-horizon"
            className="text-xs text-muted-foreground"
          >
            {`Link up to ${horizon}`}
          </div>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={autoPlace.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              autoPlace.mutate(linkHorizonRequest(linkUpTo, horizonCleared), {
                onSuccess: () => onOpenChange(false),
              });
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
