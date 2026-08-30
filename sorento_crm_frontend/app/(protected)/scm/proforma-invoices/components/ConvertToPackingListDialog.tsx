'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useProformaInvoice } from '../../hooks/useProformaInvoices';
import { EM_DASH, fmtQty } from '../../lib/format';

/**
 * How much of THIS invoice goes onto a container (AC-F10, Q9).
 *
 * One question: each line's REMAINING quantity, pre-filled, because the normal case is
 * "all of what is left" and the split is the exception that has to be typed. A convert
 * always opens a NEW draft packing list - "add to an existing draft" was dropped
 * everywhere (captain, Q6), so there is nothing to choose before the quantities.
 *
 * This is the PI DETAIL's surface only: placing part of an invoice is a deliberate act
 * made on one document. The list converts the whole selection at once, no dialog (R15).
 */
export function ConvertToPackingListDialog({
  open,
  onOpenChange,
  invoiceIds,
  pending,
  onConvert,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  invoiceIds: string[];
  pending?: boolean;
  onConvert: (args: { lineQuantities: Record<string, number> }) => void;
}) {
  const single = invoiceIds.length === 1 ? invoiceIds[0] : null;
  const { data: invoice, isLoading } = useProformaInvoice(open ? single : null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});

  // Re-read on every open: a remainder typed last time describes an invoice that has since
  // moved, and a stale figure here places the wrong quantity silently.
  useEffect(() => {
    if (!open) return;
    setQuantities({});
  }, [open]);

  const placeable = useMemo(
    () => (invoice?.lines ?? []).filter((line) => (line.remaining_qty ?? 0) > 0),
    [invoice],
  );
  /** Finished: every piece of it is on a container. */
  const alreadyPlaced = useMemo(
    () =>
      (invoice?.lines ?? []).filter(
        (line) => (line.remaining_qty ?? 0) <= 0 && (line.placed_qty ?? 0) > 0,
      ),
    [invoice],
  );
  /**
   * Nothing placed and nothing placeable - a line no container can carry YET, because its
   * item code matches no product we hold.
   *
   * Reported apart from the finished ones, and with its reason: calling it "already placed"
   * sent the reader looking for a container that never held it, and the dialog then
   * announced that every line of the invoice was in a packing list when none of them was.
   */
  const unplaceable = useMemo(
    () =>
      (invoice?.lines ?? []).filter(
        (line) => (line.remaining_qty ?? 0) <= 0 && (line.placed_qty ?? 0) <= 0,
      ),
    [invoice],
  );

  const submit = () => {
    const lineQuantities: Record<string, number> = {};
    for (const line of placeable) {
      const raw = quantities[line.id];
      if (raw === undefined || raw === '') continue;
      const parsed = Number(raw);
      if (Number.isNaN(parsed)) continue;
      lineQuantities[line.id] = parsed;
    }
    onConvert({ lineQuantities });
  };

  const invalid = placeable.some((line) => {
    const raw = quantities[line.id];
    if (raw === undefined || raw === '') return false;
    const parsed = Number(raw);
    return Number.isNaN(parsed) || parsed < 0 || parsed > (line.remaining_qty ?? 0);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Convert to a packing list</DialogTitle>
          <DialogDescription>
            {invoiceIds.length === 1
              ? 'Each line places what it has left; type a smaller figure to split it across two containers.'
              : `${invoiceIds.length} invoices. Every line places what it has left.`}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          {single && isLoading ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the invoice...
            </p>
          ) : null}

          {single && invoice ? (
            <div className="space-y-2">
              {placeable.length === 0 ? (
                <Alert>
                  <AlertDescription>
                    {alreadyPlaced.length > 0
                      ? `Every line of ${invoice.pi_number} is already in a packing list.`
                      : `No line of ${invoice.pi_number} can go on a container yet.`}
                  </AlertDescription>
                </Alert>
              ) : (
                <div className="divide-y divide-border rounded-lg border">
                  {placeable.map((line) => (
                    <div
                      key={line.id}
                      className="flex flex-col gap-2 p-2.5 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium" title={line.item_code}>
                          {line.item_code}
                        </p>
                        <p className="text-2xs text-muted-foreground">
                          {fmtQty(line.qty)} on the invoice
                          {line.placed_qty > 0
                            ? `, ${fmtQty(line.placed_qty)} already placed`
                            : ''}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Input
                          type="number"
                          min={0}
                          max={line.remaining_qty}
                          value={quantities[line.id] ?? String(line.remaining_qty)}
                          onChange={(e) =>
                            setQuantities((prev) => ({ ...prev, [line.id]: e.target.value }))
                          }
                          className="h-8 w-24 text-right tabular-nums"
                          aria-label={`Quantity to place for ${line.item_code}`}
                        />
                        <span className="text-2xs text-muted-foreground">
                          of {fmtQty(line.remaining_qty)} left
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {alreadyPlaced.length > 0 ? (
                <p className="text-2xs text-muted-foreground">
                  {alreadyPlaced.length}{' '}
                  {alreadyPlaced.length === 1 ? 'line is' : 'lines are'} already fully placed
                  and are not offered again:{' '}
                  {alreadyPlaced
                    .slice(0, 5)
                    .map((l) => l.item_code)
                    .join(', ') || EM_DASH}
                  {alreadyPlaced.length > 5 ? ` and ${alreadyPlaced.length - 5} more` : ''}.
                </p>
              ) : null}
              {unplaceable.length > 0 ? (
                <div className="space-y-1 rounded-lg border border-dashed p-2.5">
                  <p className="text-2xs font-medium">Cannot go on a container yet</p>
                  {unplaceable.map((line) => (
                    <p key={line.id} className="text-2xs text-muted-foreground">
                      <span className="font-medium">{line.item_code}</span>
                      {' - '}
                      {line.unmatched_reason ??
                        'no catalogue product for this code, so there is nowhere to ship it.'}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {invalid ? (
            <Alert variant="destructive">
              <AlertDescription>
                A quantity cannot be negative, and cannot be more than the line has left.
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={pending || invalid || (!!single && placeable.length === 0)}
          >
            {pending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Convert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConvertToPackingListDialog;
