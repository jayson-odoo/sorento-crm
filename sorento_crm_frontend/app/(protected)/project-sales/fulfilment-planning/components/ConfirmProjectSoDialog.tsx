'use client';

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

/**
 * The one confirmation for the whole sales order (AC-C01, AC-G03).
 *
 * It names the sales order and how many lines go with it, because that is what the press
 * commits, and it says plainly that this cannot be undone: the components become claims on
 * stock, the Buy residual reaches purchasing, and a later change goes through a new
 * revision rather than an edit. Reconfirming supersedes the revision in place, so the copy
 * says which of the two is about to happen.
 */
export function ConfirmProjectSoDialog({
  reference,
  lineCount,
  currentRevision,
  submitting,
  onDone,
  onConfirm,
}: {
  reference: string;
  lineCount: number;
  /** The revision this one replaces, when the order has been confirmed before. */
  currentRevision?: number | null;
  submitting: boolean;
  onDone: () => void;
  onConfirm: () => void;
}) {
  const lines = `${lineCount} line${lineCount === 1 ? '' : 's'}`;
  return (
    <AlertDialog open onOpenChange={(next) => !next && onDone()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{`Confirm ${reference}?`}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                {currentRevision
                  ? `All ${lines} are confirmed together and supersede revision ${currentRevision}.`
                  : `All ${lines} are confirmed together.`}
              </p>
              <p>
                The composition is frozen and the Buy residual goes to purchasing. This
                action cannot be undone.
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={submitting}
            onClick={(event) => {
              event.preventDefault();
              onConfirm();
            }}
          >
            {submitting ? 'Confirming…' : 'Confirm the sales order'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
