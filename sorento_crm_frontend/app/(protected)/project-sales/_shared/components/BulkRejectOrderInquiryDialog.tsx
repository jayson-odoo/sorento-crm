'use client';

import * as React from 'react';
import { LoaderCircle } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useOrderInquiryHandshake } from '../hooks/useOrderInquiry';

/**
 * Purchasing refuses a BATCH, with ONE reason (item 15, R8).
 *
 * Reject was a per-row button until the row actions column went. The reason is asked for
 * once and carried onto every ticked row, because twenty rows refused for the same
 * closed factory is one fact, not twenty. Same shape as the single-row dialog it
 * replaces: an `AlertDialog`, a required reason, a destructive confirm.
 */
export function BulkRejectOrderInquiryDialog({
  rowIds,
  open,
  onOpenChange,
  onRejected,
}: {
  rowIds: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Clears the page's selection once the batch went through. */
  onRejected?: () => void;
}) {
  const { rejectRows } = useOrderInquiryHandshake();
  const [reason, setReason] = React.useState('');
  const [touched, setTouched] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setReason('');
      setTouched(false);
    }
  }, [open]);

  function submit() {
    setTouched(true);
    const text = reason.trim();
    if (!text || rowIds.length === 0) return;
    rejectRows.mutate(
      { rowIds, reason: text },
      {
        onSuccess: () => {
          onRejected?.();
          onOpenChange(false);
        },
      },
    );
  }

  const count = rowIds.length;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {count === 1 ? 'Reject 1 row?' : `Reject ${count} rows?`}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {/* What the action does, in the words of the action. */}
            Rejects {count === 1 ? 'this row' : 'these rows'} with your reason and gives
            back whatever they hold. CS decides the lines again.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1.5">
          <Label className="block">
            Reason <span className="text-destructive">*</span>
          </Label>
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why can this not be bought? e.g. the factory is closed until November"
            rows={3}
            autoFocus
          />
          {touched && !reason.trim() ? (
            <p className="text-2xs text-destructive">A reason is required to reject.</p>
          ) : null}
        </div>

        <AlertDialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={rejectRows.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={rejectRows.isPending || count === 0}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {rejectRows.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            {count === 1 ? 'Reject row' : `Reject ${count} rows`}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default BulkRejectOrderInquiryDialog;
