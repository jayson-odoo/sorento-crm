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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAutoPlaceOrderInquiryRows } from '../hooks/useOrderInquiry';
import { horizonSentence, linkHorizonRequest } from '../lib/linkHorizon';

/**
 * "Auto link all" (AC-D9; the captain, 20 Aug: "we need to link already at first already
 * instead of suggesting and needing the users to click 1 by 1"). Runs the cascade over
 * the whole worklist now, rather than waiting for the moments it already runs
 * automatically (a raise, an outstanding PO import, a PO confirm). Confirmed like any
 * bulk write: it links real document lines and writes the audit claim behind each one.
 *
 * THE DATE LIVES HERE (item 12). It used to sit on the toolbar, shared by four presses
 * that each meant something different by it, and it was the widest thing in the right
 * cluster. This is the one press it actually governs, so the box moved into the press
 * and the toolbar became one row. The value still starts from the page's own precedence
 * (the URL, then this browser, then the plan's horizon) and is handed back so the page
 * keeps remembering it.
 */
export function AutoLinkOrderInquiryDialog({
  open,
  onOpenChange,
  linkUpTo = '',
  horizonCleared = false,
  onHorizonChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The page's cut off date, `YYYY-MM-DD`, or blank. */
  linkUpTo?: string;
  /** The buyer took the horizon off, as opposed to never having set one (S1). */
  horizonCleared?: boolean;
  /**
   * The date the buyer chose in this dialog, handed back so the page remembers it the
   * same way it always has - in the URL and in this browser. Without this the choice
   * would live and die inside one press.
   */
  onHorizonChange?: (value: string, cleared: boolean) => void;
}) {
  const autoPlace = useAutoPlaceOrderInquiryRows();
  // Edited here, published to the page on change: the dialog is the control now, and a
  // date that only took effect on Confirm could not be read back anywhere else.
  const horizon = horizonSentence(linkUpTo, horizonCleared);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Auto link all</AlertDialogTitle>
          <AlertDialogDescription>
            Link open order rows to outstanding documents, nearest location and earliest
            purchase order first?
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="auto-link-cut-off">Purchase order cut off</Label>
          <Input
            id="auto-link-cut-off"
            data-testid="auto-link-cut-off"
            type="date"
            value={linkUpTo}
            onChange={(event) =>
              // Emptying the box is a DECISION - "no horizon" - and not the same as
              // never having chosen (S1).
              onHorizonChange?.(event.target.value, !event.target.value)
            }
          />
          {/* The horizon this press runs to, worded exactly as the manual Link dialog
              words it. A fact and a date, never an explanation of what a horizon is. */}
          {horizon ? (
            <p data-testid="auto-link-horizon" className="text-xs text-muted-foreground">
              {horizon}
            </p>
          ) : null}
        </div>

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
            Auto link all
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
