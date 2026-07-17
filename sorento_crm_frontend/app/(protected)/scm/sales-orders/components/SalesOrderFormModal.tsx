'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
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

// `uom` is display-only (product base UOM, stamped by the BE) — it is carried
// for existing lines but never sent on write.
type LineDraft = { sku: string; qty_ordered: string; uom: string };

const emptyLine = (): LineDraft => ({ sku: '', qty_ordered: '', uom: '' });

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
        })),
      );
    } else {
      setOrderType('');
      setCustomer('');
      setPriority('normal');
      setRequestedDate('');
      setLines([emptyLine()]);
    }
    setError(null);
  }, [open, editing]);

  const segment = useMemo(
    () => customerOptions.data?.find((c) => c.value === customer)?.description ?? null,
    [customer, customerOptions.data],
  );

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
    await onSubmit({
      order_type: orderType,
      customer_code: customer,
      priority,
      requested_delivery_date: requestedDate || null,
      lines: cleanedLines,
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
                      options={productOptions.data ?? []}
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
                      {line.uom || '—'}
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
