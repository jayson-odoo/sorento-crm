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
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { MirrorAnnotationCard } from '@/components/common/MirrorAnnotationCard';
import {
  useCustomerOptions,
  useOrderTypeOptions,
  useProductOptions,
} from '../../hooks/useScmOptions';
import { useAnnotateSalesOrder } from '../../hooks/useSalesOrders';
import { fmtDate, fmtInt, fmtMoney } from '../../lib/format';
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium break-words">{children}</span>
    </div>
  );
}

/**
 * Read-only surface for an AutoCount-mirrored sales order. The SO list has no
 * dedicated detail page, so the form modal doubles as the mirror detail view:
 * it renders the header, meta, and read-only pricing lines, plus the ONE allowed
 * edit — the internal-note / follow-up annotation via `MirrorAnnotationCard`.
 * Every mutating input/Save is deliberately absent (the BE 403s them anyway).
 */
function ReadOnlySalesOrderView({
  so,
  onOpenChange,
}: {
  so: SalesOrder;
  onOpenChange: (open: boolean) => void;
}) {
  const annotate = useAnnotateSalesOrder();
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2">
          <span className="break-words">{so.so_number}</span>
          <AutoCountSourceBadge source="autocount" />
        </DialogTitle>
      </DialogHeader>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Customer">{so.customer_name || so.customer_code || '—'}</Field>
          <Field label="Doc No">{so.source_doc_no || '—'}</Field>
          <Field label="Type">{so.order_type_label || so.order_type || '—'}</Field>
          <Field label="Status">
            <Badge variant="secondary" appearance="light">
              {so.status.replace(/[_-]+/g, ' ')}
            </Badge>
          </Field>
          <Field label="Order date">{fmtDate(so.order_date)}</Field>
          <Field label="Requested delivery">{fmtDate(so.requested_delivery_date)}</Field>
          <Field label="Total qty">{fmtInt(so.total_qty)}</Field>
          <Field label="Committed qty">{fmtInt(so.committed_qty)}</Field>
        </div>

        <div>
          <Label className="mb-2 block">Lines</Label>
          {so.lines.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30 text-left text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Product</th>
                    <th className="px-3 py-2 font-medium">UoM</th>
                    <th className="px-3 py-2 text-right font-medium">Qty</th>
                    <th className="px-3 py-2 text-right font-medium">Unit price</th>
                    <th className="px-3 py-2 text-right font-medium">Discount</th>
                    <th className="px-3 py-2 font-medium">Tax</th>
                    <th className="px-3 py-2 text-right font-medium">Tax amt</th>
                    <th className="px-3 py-2 text-right font-medium">Sub total</th>
                    <th className="px-3 py-2 font-medium">Delivery date</th>
                  </tr>
                </thead>
                <tbody>
                  {so.lines.map((l) => (
                    <tr key={l.id} className="border-b align-top last:border-0">
                      <td className="px-3 py-2">
                        <span className="font-medium">{l.sku}</span>
                        {l.product_name && l.product_name !== l.sku ? (
                          <span
                            className="block max-w-xs truncate text-muted-foreground"
                            title={l.product_name}
                          >
                            {l.product_name}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">{l.uom || '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtInt(l.qty_ordered)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(l.unit_price)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {fmtMoney(l.discount_amt)}
                      </td>
                      <td className="px-3 py-2">
                        {l.tax_code || '—'}
                        {l.tax_rate !== null && l.tax_rate !== undefined
                          ? ` (${l.tax_rate}%)`
                          : ''}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(l.tax_amt)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(l.sub_total)}</td>
                      <td className="px-3 py-2">{fmtDate(l.delivery_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">This sales order has no lines.</p>
          )}
        </div>

        <MirrorAnnotationCard
          value={{ internal_note: so.internal_note, follow_up: so.follow_up }}
          isSaving={annotate.isPending}
          onSave={(next) => annotate.mutate({ id: so.id, data: next })}
        />
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          Close
        </Button>
      </DialogFooter>
    </>
  );
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

  const isAutocount = editing?.source === 'autocount';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        {isAutocount && editing ? (
          <ReadOnlySalesOrderView so={editing} onOpenChange={onOpenChange} />
        ) : (
          <>
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
