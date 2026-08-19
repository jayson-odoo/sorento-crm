'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { LoaderCircleIcon, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  useCustomerOptions,
  useOrderTypeOptions,
  useProductOptions,
} from '../../hooks/useScmOptions';
import type {
  SalesOrder,
  SalesOrderFormData,
  SalesOrderPriority,
} from '../../types/scm.types';

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

// `uom` is display-only (product base UOM, stamped by the BE) - it is carried
// for existing lines but never sent on write. `product_name` is likewise display-only:
// it seeds the Product select's option for a line whose SKU is not in the (paged, top
// -100-by-code) product dropdown, so an edited line with a code late in the catalogue
// still shows its product instead of rendering blank.
type LineDraft = { sku: string; qty_ordered: string; uom: string; product_name?: string };

const emptyLine = (): LineDraft => ({ sku: '', qty_ordered: '', uom: '' });

/** `sku|qty` per line, order-independent, so a re-save with the same lines in a
 * different order is not read as a change. Used to decide whether `lines` rides on the
 * write payload at all - see the note on `handleSubmit` below. */
function lineSignature(ls: { sku: string; qty_ordered: number }[]): string {
  return ls
    .map((l) => `${l.sku}|${l.qty_ordered}`)
    .sort()
    .join(',');
}

export function SalesOrderFormModal({
  open,
  onOpenChange,
  editing,
  onSubmit,
  isPending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: SalesOrder | null;
  onSubmit: (data: SalesOrderFormData) => Promise<void>;
  isPending: boolean;
}) {
  const [orderType, setOrderType] = useState('');
  const [customer, setCustomer] = useState('');
  const [priority, setPriority] = useState<SalesOrderPriority>('normal');
  const [requestedDate, setRequestedDate] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  // What the order's lines looked like when the modal opened, so `handleSubmit` can tell
  // "nothing about the lines changed" from "the person edited a line" - see the note
  // there. Empty/null while creating, where lines are always sent.
  const originalLineSignatureRef = useRef<string | null>(null);

  const orderTypeOptions = useOrderTypeOptions();
  const customerOptions = useCustomerOptions();
  const productOptions = useProductOptions();

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setOrderType(editing.order_type);
      setCustomer(editing.customer_code);
      setPriority(editing.priority);
      setRequestedDate(editing.requested_delivery_date?.slice(0, 10) ?? '');
      setLines(
        editing.lines.map((l) => ({
          sku: l.sku,
          qty_ordered: String(l.qty_ordered),
          uom: l.uom,
          product_name: l.product_name,
        })),
      );
      originalLineSignatureRef.current = lineSignature(
        editing.lines.map((l) => ({ sku: l.sku, qty_ordered: l.qty_ordered })),
      );
    } else {
      setOrderType('');
      setCustomer('');
      setPriority('normal');
      setRequestedDate('');
      setLines([emptyLine()]);
      originalLineSignatureRef.current = null;
    }
    setError(null);
  }, [open, editing]);

  const segment = useMemo(
    () => customerOptions.data?.find((c) => c.value === customer)?.description ?? null,
    [customer, customerOptions.data],
  );

  // The Product dropdown is server-paged (top 100 by code), so a line whose SKU sorts
  // past page one - routine on a large catalogue - is not among `productOptions.data`
  // and the SearchableSelect renders it blank even though the line's own `sku` is set
  // correctly. Widen the option list with each edited order's own lines so every line
  // it opened with always resolves to a real product, never a blank trigger.
  const mergedProductOptions = useMemo(() => {
    const base = productOptions.data ?? [];
    if (!editing) return base;
    const known = new Set(base.map((o) => o.value));
    const extra: SearchableSelectOption[] = [];
    for (const l of editing.lines) {
      if (!l.sku || known.has(l.sku)) continue;
      known.add(l.sku);
      extra.push({
        value: l.sku,
        label: l.product_name ? `${l.sku} · ${l.product_name}` : l.sku,
      });
    }
    return extra.length ? [...base, ...extra] : base;
  }, [productOptions.data, editing]);

  const updateLine = (idx: number, patch: Partial<LineDraft>) => {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!orderType) return setError('Select an order type.');
    if (!customer) return setError('Select a customer.');
    // uom is display-only and dropped by the service before the write payload.
    const cleanedLines = lines
      .filter((l) => l.sku && Number(l.qty_ordered) > 0)
      .map((l) => ({ sku: l.sku, qty_ordered: Number(l.qty_ordered), uom: l.uom }));
    if (cleanedLines.length === 0) {
      return setError('Add at least one line with a product and quantity.');
    }
    // Editing an existing order whose lines are exactly what it opened with is a
    // header-only save (order type, customer, dates) - `lines` is left OFF the payload
    // so the BE leaves them, and whatever warehouse each carries, untouched. Sending the
    // same lines back would still be read as "replace them", which is how editing just
    // the order type used to wipe every line's stock location. A real line edit (added,
    // removed, re-picked product, changed qty) still sends the full set, same as today.
    const linesUnchanged =
      editing !== null &&
      originalLineSignatureRef.current !== null &&
      lineSignature(cleanedLines.map((l) => ({ sku: l.sku, qty_ordered: l.qty_ordered }))) ===
        originalLineSignatureRef.current;
    await onSubmit({
      order_type: orderType,
      customer_code: customer,
      priority,
      requested_delivery_date: requestedDate || null,
      ...(linesUnchanged ? {} : { lines: cleanedLines }),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit sales order' : 'Add sales order'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label className="mb-1 block">Order type</Label>
              <SearchableSelect
                value={orderType}
                onChange={setOrderType}
                options={orderTypeOptions.data ?? []}
                placeholder="Select type"
              />
            </div>
            <div>
              <Label className="mb-1 block">Customer</Label>
              <SearchableSelect
                value={customer}
                onChange={setCustomer}
                options={customerOptions.data ?? []}
                placeholder="Select customer"
              />
              {segment ? (
                <p className="mt-1 text-2xs text-muted-foreground">Segment: {segment}</p>
              ) : null}
            </div>
            <div>
              <Label className="mb-1 block">Priority</Label>
              <SearchableSelect
                value={priority}
                onChange={(v) => setPriority((v || 'normal') as SalesOrderPriority)}
                options={PRIORITY_OPTIONS}
                placeholder="Select priority"
              />
            </div>
            <div>
              <Label className="mb-1 block">Requested delivery date</Label>
              <Input
                type="date"
                value={requestedDate}
                onChange={(e) => setRequestedDate(e.target.value)}
              />
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label>Lines</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLines((prev) => [...prev, emptyLine()])}
              >
                <Plus className="size-4" />
                Add line
              </Button>
            </div>
            <div className="space-y-2">
              {lines.map((line, idx) => (
                <div key={idx} className="flex items-end gap-2">
                  <div className="flex-1">
                    {idx === 0 ? (
                      <Label className="mb-1 block text-2xs text-muted-foreground">Product</Label>
                    ) : null}
                    <SearchableSelect
                      value={line.sku}
                      onChange={(v) => updateLine(idx, { sku: v })}
                      options={mergedProductOptions}
                      placeholder="Select product"
                    />
                  </div>
                  <div className="w-24">
                    {idx === 0 ? (
                      <Label className="mb-1 block text-2xs text-muted-foreground">Qty</Label>
                    ) : null}
                    <Input
                      type="number"
                      min={0}
                      value={line.qty_ordered}
                      onChange={(e) => updateLine(idx, { qty_ordered: e.target.value })}
                      className="text-right tabular-nums"
                    />
                  </div>
                  <div className="w-24">
                    {idx === 0 ? (
                      <Label className="mb-1 block text-2xs text-muted-foreground">UoM</Label>
                    ) : null}
                    {/* Display-only: the BE stamps UoM from the product's base UOM. */}
                    <div
                      className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground"
                      title="Set automatically from the product's base unit of measure"
                    >
                      {line.uom || '-'}
                    </div>
                  </div>
                  <Button
                    type="button"
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    disabled={lines.length === 1}
                    onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}
                    aria-label="Remove line"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? <LoaderCircleIcon className="me-2 size-4 animate-spin" /> : null}
              {editing ? 'Save changes' : 'Create sales order'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
