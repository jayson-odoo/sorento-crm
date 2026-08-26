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
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDraftShipments, useProformaInvoice } from '../../hooks/useProformaInvoices';
import { EM_DASH, fmtDate, fmtQty } from '../../lib/format';

/**
 * How much of these invoices goes into which packing list (AC-F10).
 *
 * Two questions, in the order they are asked. WHERE: a new draft, or one of this supplier's
 * drafts that is still open - a container is loaded over several days and the second
 * factory's invoice belongs in the box the first one is already in. HOW MUCH: each line's
 * REMAINING quantity, pre-filled, because the normal case is "all of what is left" and the
 * split is the exception that has to be typed.
 *
 * Per-line editing is offered for ONE invoice at a time. On a multi-invoice convert the
 * lines of five documents in one dialog is a worse surface than the rule the backend
 * already applies - every line places what it has left - so the dialog says that instead.
 */
export function ConvertToPackingListDialog({
  open,
  onOpenChange,
  invoiceIds,
  supplierId,
  pending,
  onConvert,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  invoiceIds: string[];
  /** Whose drafts to offer. Null on a mixed selection - then every draft is offered. */
  supplierId?: string | null;
  pending?: boolean;
  onConvert: (args: {
    lineQuantities: Record<string, number>;
    targetShipmentId: string | null;
  }) => void;
}) {
  const single = invoiceIds.length === 1 ? invoiceIds[0] : null;
  const { data: invoice, isLoading } = useProformaInvoice(open ? single : null);
  const drafts = useDraftShipments(supplierId ?? null, open);
  const [targetShipmentId, setTargetShipmentId] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});

  // Re-read on every open: a remainder typed last time describes an invoice that has since
  // moved, and a stale figure here places the wrong quantity silently.
  useEffect(() => {
    if (!open) return;
    setTargetShipmentId(null);
    setQuantities({});
  }, [open]);

  const placeable = useMemo(
    () => (invoice?.lines ?? []).filter((line) => (line.remaining_qty ?? 0) > 0),
    [invoice],
  );
  const alreadyPlaced = useMemo(
    () => (invoice?.lines ?? []).filter((line) => (line.remaining_qty ?? 0) <= 0),
    [invoice],
  );

  const draftOptions = useMemo(
    () =>
      (drafts.data ?? []).map((d) => ({
        value: d.shipment_id,
        label: `${d.shipment_number ?? 'Draft'} - ${fmtDate(d.shipment_date)} - ${d.lines} lines`,
        description: d.supplier_names.join(', ') || undefined,
      })),
    [drafts.data],
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
    onConvert({ lineQuantities, targetShipmentId });
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
          <div>
            <Label htmlFor="convert-target" className="mb-1 block text-xs">
              Packing list
            </Label>
            <SearchableSelect
              id="convert-target"
              value={targetShipmentId ?? ''}
              onChange={(v: string) => setTargetShipmentId(v || null)}
              options={draftOptions}
              placeholder="Create a new draft packing list"
              emptyMessage="No draft packing list open for this supplier."
              clearable
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to start a new one.
            </p>
          </div>

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
                    Every line of {invoice.pi_number} is already in a packing list.
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
