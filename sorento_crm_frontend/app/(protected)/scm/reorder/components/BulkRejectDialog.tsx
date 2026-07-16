'use client';

import { useEffect, useState } from 'react';
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

/**
 * Bulk Reject (M4-D8/D9) — destructive confirm with ONE shared, required reason
 * applied to every selected pending recommendation. Count-bearing title.
 */
export function BulkRejectDialog({
  count,
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  count: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (reason: string) => void;
  isSubmitting: boolean;
}) {
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (open) {
      setReason('');
      setTouched(false);
    }
  }, [open]);

  const submit = () => {
    setTouched(true);
    if (!reason.trim()) return;
    onSubmit(reason.trim());
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Reject {count} recommendation{count === 1 ? '' : 's'}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            The selected recommendations will be dismissed and won&apos;t draft purchase orders.
            This can&apos;t be undone. The reason is applied to all of them.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1.5">
          <Label className="block">
            Reason <span className="text-destructive">*</span>
          </Label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why reject these? e.g. overstocked, demand spike was one-off…"
            rows={3}
            autoFocus
          />
          {touched && !reason.trim() ? (
            <p className="text-2xs text-destructive">A reason is required to reject.</p>
          ) : null}
        </div>

        <AlertDialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={isSubmitting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Reject {count === 1 ? 'recommendation' : `${count} recommendations`}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
