'use client';

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

/**
 * The over-capacity refusal, and the way past it (AC-E5).
 *
 * Shared by the invoice detail and the list's bulk convert because both raise the same
 * refusal from the same endpoint, and a second copy of it would be a second wording of the
 * one sentence that has to name the figures.
 *
 * The reason is REQUIRED. A container knowingly loaded past its planned volume is a
 * decision somebody made, and "convert anyway" with nothing written down is exactly the
 * state that cannot be explained a month later when the box will not close.
 */
export function OverCapacityDialog({
  message,
  reason,
  onReasonChange,
  onCancel,
  onConfirm,
  pending,
}: {
  /** The server's refusal, which names the volume and the capacity. Null = closed. */
  message: string | null;
  reason: string;
  onReasonChange: (next: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
  pending?: boolean;
}) {
  return (
    <AlertDialog open={!!message} onOpenChange={(o) => !o && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>This will not fit</AlertDialogTitle>
          <AlertDialogDescription>{message}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="pi-override-reason" className="text-xs">
            Why convert anyway
          </Label>
          <Textarea
            id="pi-override-reason"
            value={reason}
            onChange={(e) => onReasonChange(e.target.value)}
            rows={3}
            placeholder="Second container booked for the overflow"
          />
        </div>
        <AlertDialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={!reason.trim() || pending}>
            Convert anyway
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default OverCapacityDialog;
