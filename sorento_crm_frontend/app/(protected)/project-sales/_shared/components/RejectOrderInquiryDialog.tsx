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
 * Purchasing refuses one instruction, with a reason (AC-H5).
 *
 * The same shape the plan's own reject already has (`scm/reorder`'s BulkRejectDialog): an
 * `AlertDialog`, a required reason, a destructive confirm. The reason is not paperwork -
 * it is what CS reads on the board cell when the line comes back to them, so an empty one
 * is refused here as well as at the server.
 */
export function RejectOrderInquiryDialog({
  rowId,
  itemCode,
  open,
  onOpenChange,
}: {
  rowId: string;
  itemCode?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { reject } = useOrderInquiryHandshake();
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
    if (!text) return;
    reject.mutate(
      { rowId, reason: text },
      { onSuccess: () => onOpenChange(false) },
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {itemCode ? `Reject ${itemCode}?` : 'Reject this row?'}
          </AlertDialogTitle>
          <AlertDialogDescription>
            The row stops counting as demand and the sales-order line goes back to CS to be
            decided again. They see the reason on the line.
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
            disabled={reject.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={reject.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {reject.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Reject row
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default RejectOrderInquiryDialog;
