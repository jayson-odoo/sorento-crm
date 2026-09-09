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
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useContainerSizes } from '../../hooks/useFulfilment';
import { useProformaInvoice } from '../../hooks/useProformaInvoices';
import { useProformaInvoicePacking } from '../../hooks/useProformaInvoicePacking';
import { EM_DASH, fmtQty, fmtTrimmedDecimal } from '../../lib/format';
import type { ProformaInvoicePackingLine } from '../types/packingLine.types';

/**
 * How much of THIS invoice goes onto a container (AC-F10, Q9), and which container (S5,
 * ruling 1).
 *
 * The per-line quantity question is the PI DETAIL's own: placing part of an invoice is a
 * deliberate act made on one document, so the list converts its whole selection at once and
 * never sees that part of the body (R15, `single` stays null for a multi-invoice convert).
 * The Container size select is common to both surfaces, because both are the SAME write
 * (`convert_to_draft_shipment`) and the box being loaded is a property of the shipment
 * either way.
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
  onConvert: (args: {
    lineQuantities: Record<string, number>;
    containerSizeId: string | null;
  }) => void;
}) {
  const single = invoiceIds.length === 1 ? invoiceIds[0] : null;
  const { data: invoice, isLoading } = useProformaInvoice(open ? single : null);
  const packing = useProformaInvoicePacking(open ? invoice : undefined);
  const packingRows = useMemo(() => packing.data?.rows ?? [], [packing.data]);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const containerSizes = useContainerSizes();
  const [containerSizeId, setContainerSizeId] = useState<string | null>(null);
  // A packing row placed whole or not at all (S4, AC-D2b) - every MATCHED row starts
  // checked (placed), the same default the plan rules for "default all unplaced" rows on
  // a PI nothing has convertED yet.
  const [placedRowIds, setPlacedRowIds] = useState<Set<string>>(new Set());

  // Re-read on every open: a remainder typed last time describes an invoice that has since
  // moved, and a stale figure here places the wrong quantity silently. The size resets to
  // the tenant default too - a size chosen for a previous convert says nothing about this
  // one.
  useEffect(() => {
    if (!open) return;
    setQuantities({});
    setContainerSizeId(null);
  }, [open]);

  // Rows default to placed the moment they arrive - a checkbox nobody has touched yet
  // reads as "everything goes", which is the plan's own default.
  useEffect(() => {
    if (!open) return;
    setPlacedRowIds(new Set(packingRows.filter((r) => r.match_state === 'matched').map((r) => r.id)));
  }, [open, packingRows]);

  /** Every MATCHED packing row for one invoice line - the rows a whole-row checkbox set
   *  offers for it, in place of a quantity input (AC-D2b: a line WITH rows places them
   *  whole, never part of one). */
  const rowsForLine = (lineId: string): ProformaInvoicePackingLine[] =>
    packingRows.filter((r) => r.proforma_invoice_line_id === lineId && r.match_state === 'matched');

  /** Container / seal / BL carried onto the draft (AC-D2c) - agreeing rows prefill it,
   *  disagreeing ones leave it blank and name the conflict. Phase 1 mock: packing rows
   *  carry a container number only (no seal on the row shape, AC-B1); BL comes off the
   *  invoice's own header field, which every row of one PI necessarily shares. */
  const headerCarryOver = useMemo(() => {
    const containers = new Set(
      packingRows.filter((r) => r.match_state === 'matched' && r.container_no).map((r) => r.container_no),
    );
    const container = containers.size === 1 ? [...containers][0] : null;
    return {
      container,
      conflict: containers.size > 1,
      bl: invoice?.bl_no ?? null,
    };
  }, [packingRows, invoice?.bl_no]);

  const defaultSize = useMemo(
    () => (containerSizes.data ?? []).find((s) => s.is_default) ?? null,
    [containerSizes.data],
  );
  const containerSizeOptions = useMemo(
    () =>
      (containerSizes.data ?? []).map((s) => ({
        value: s.id,
        label: `${s.code} - ${fmtTrimmedDecimal(s.cbm, 2)} cbm${s.is_default ? ' (default)' : ''}`,
      })),
    [containerSizes.data],
  );

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
    onConvert({ lineQuantities, containerSizeId });
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
          <div className="space-y-1.5">
            <Label htmlFor="convert-container-size" className="text-xs">
              Container size
            </Label>
            <SearchableSelect
              id="convert-container-size"
              size="sm"
              value={containerSizeId ?? ''}
              onChange={(v: string) => setContainerSizeId(v || null)}
              options={containerSizeOptions}
              placeholder={
                defaultSize
                  ? `${defaultSize.code} - ${fmtTrimmedDecimal(defaultSize.cbm, 2)} cbm (default)`
                  : 'Default size'
              }
              clearable
            />
          </div>

          {single && isLoading ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the invoice...
            </p>
          ) : null}

          {single && invoice ? (
            <div className="space-y-2">
              {/* Header carry-over (S4, AC-D2c) - shown whether or not there is anything
                  to place, since it is a fact about the packing rows, not the selection. */}
              {packingRows.length > 0 ? (
                <div className="rounded-lg border border-dashed p-2.5 text-2xs">
                  <p className="font-medium text-foreground">Carried onto the draft</p>
                  {headerCarryOver.conflict ? (
                    <p className="text-muted-foreground">
                      Container - the packing rows name more than one; left blank.
                    </p>
                  ) : (
                    <p className="text-muted-foreground">
                      Container {headerCarryOver.container ?? EM_DASH}
                      {headerCarryOver.bl ? ` · BL ${headerCarryOver.bl}` : ''}
                    </p>
                  )}
                </div>
              ) : null}
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
                  {placeable.map((line) => {
                    const rows = rowsForLine(line.id);
                    return (
                    <div key={line.id} className="flex flex-col gap-2 p-2.5">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
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
                        {rows.length === 0 ? (
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
                        ) : null}
                      </div>
                      {/* Placed whole or not at all (AC-D2b) - a packing row is a
                          checkbox, never a quantity: the supplier packed this many
                          cartons of it and there is no "part of a carton". */}
                      {rows.length > 0 ? (
                        <ul className="space-y-1 ps-1">
                          {rows.map((row) => (
                            <li key={row.id} className="flex items-center gap-2 text-2xs">
                              <Checkbox
                                id={`packing-row-${row.id}`}
                                checked={placedRowIds.has(row.id)}
                                onCheckedChange={(checked) =>
                                  setPlacedRowIds((prev) => {
                                    const next = new Set(prev);
                                    if (checked) next.add(row.id);
                                    else next.delete(row.id);
                                    return next;
                                  })
                                }
                              />
                              <Label htmlFor={`packing-row-${row.id}`} className="cursor-pointer font-normal">
                                Row {row.row_no} - {fmtQty(row.qty)}
                                {row.cartons != null ? ` · ${fmtQty(row.cartons)} ctn` : ''}
                                {row.cbm_total != null ? ` · ${fmtTrimmedDecimal(row.cbm_total, 3)} cbm` : ''}
                              </Label>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    );
                  })}
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
