'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { ColumnState } from '../lib/scheduleTotals';
import type { DeliveryScheduleConfirmBody } from '../../../_shared/types/deliverySchedule.types';

/**
 * Confirm, and the one way past a column that does not add up.
 *
 * Refused while anything is unreconciled, but not permanently: a customer's schedule can be
 * genuinely at odds with the PO and still be the document everyone is working to, so the way
 * through is an explicit acknowledgement with a reason that stays on the record, never a
 * silent pass.
 */
export function DeliveryScheduleConfirmDialog({
  open,
  onOpenChange,
  blocking,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  blocking: ColumnState[];
  pending: boolean;
  onConfirm: (body: DeliveryScheduleConfirmBody) => Promise<void> | void;
}) {
  const [acknowledge, setAcknowledge] = React.useState(false);
  const [reason, setReason] = React.useState('');

  React.useEffect(() => {
    if (!open) {
      setAcknowledge(false);
      setReason('');
    }
  }, [open]);

  const hasBlockers = blocking.length > 0;
  const blocked = hasBlockers && (!acknowledge || reason.trim().length === 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Confirm this schedule</DialogTitle>
          <DialogDescription>
            {hasBlockers
              ? `${blocking.length} column${
                  blocking.length === 1 ? ' does' : 's do'
                } not add up yet.`
              : 'Every column agrees with the PO. Its phases go onto the project.'}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (blocked) return;
            await onConfirm(
              hasBlockers
                ? { acknowledge_unreconciled: true, reason: reason.trim() }
                : {},
            );
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            {hasBlockers && (
              <ul className="space-y-2">
                {blocking.map((column) => (
                  <li
                    key={column.key}
                    className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2"
                  >
                    <p className="truncate text-sm font-medium">
                      {column.productCode ?? column.customerCode ?? 'Unidentified column'}
                    </p>
                    <ul className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                      {column.blockers.map((blocker) => (
                        <li key={blocker.code}>{blocker.detail}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}

            {hasBlockers && (
              <div className="space-y-3">
                <label className="flex items-start gap-2 text-sm">
                  <Checkbox
                    checked={acknowledge}
                    onCheckedChange={(next) => setAcknowledge(next === true)}
                    aria-label="Confirm anyway"
                    className="mt-0.5"
                  />
                  <span>Confirm anyway</span>
                </label>

                {acknowledge && (
                  <div className="space-y-1.5">
                    <Label htmlFor="schedule-ack-reason">
                      Reason <span className="text-destructive">*</span>
                    </Label>
                    <Textarea
                      id="schedule-ack-reason"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      rows={3}
                      placeholder="What the customer said about the difference"
                    />
                  </div>
                )}
              </div>
            )}
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked || pending}>
              {pending ? 'Confirming…' : 'Confirm schedule'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
