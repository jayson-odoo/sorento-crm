'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search, X } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { DOLookupItem, lookupDeliveryOrders } from '../lib/portal-client';
import {
  PeriodPicker,
  PeriodValue,
  periodToIsoBounds,
} from './PeriodPicker';

interface Props {
  id?: string;
  value: string[];
  onChange: (next: string[], items?: DOLookupItem[]) => void;
  disabled?: boolean;
}

/**
 * DO multi-select with a filter dialog.
 *
 * Chips render selected DO numbers. The "Search & select" button opens a
 * dialog where the user can filter by date range, product code, and customer
 * (debtor) name to narrow down results, then check rows to select.
 */
export function DOFilterMultiSelect({ id, value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [period, setPeriod] = useState<PeriodValue>({ granularity: 'day' });
  const [productCode, setProductCode] = useState('');
  const [customer, setCustomer] = useState('');
  const [results, setResults] = useState<DOLookupItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftSelected, setDraftSelected] = useState<Set<string>>(new Set());
  const [draftItems, setDraftItems] = useState<DOLookupItem[]>([]);

  const runSearch = useCallback(async () => {
    const bounds = periodToIsoBounds(period);
    setLoading(true);
    setError(null);
    try {
      const items = await lookupDeliveryOrders('', 50, {
        start_date: bounds.start_date,
        end_date: bounds.end_date,
        product_code: productCode.trim() || undefined,
        debtor_name: customer.trim() || undefined,
      });
      setResults(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load delivery orders.');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [period, productCode, customer]);

  // Auto-load when the dialog opens with current selection seeded.
  useEffect(() => {
    if (!open) return;
    setDraftSelected(new Set(value));
    void runSearch();
    // Only re-run on dialog open; user re-runs manually via Search button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const toggleRow = (row: DOLookupItem) => {
    setDraftSelected((prev) => {
      const next = new Set(prev);
      if (next.has(row.order_number)) next.delete(row.order_number);
      else next.add(row.order_number);
      return next;
    });
    setDraftItems((prev) => {
      const exists = prev.some((p) => p.order_number === row.order_number);
      if (exists) return prev.filter((p) => p.order_number !== row.order_number);
      return [...prev, row];
    });
  };

  const handleApply = () => {
    const orderNumbers = Array.from(draftSelected);
    // Keep DOLookupItems aligned with the final selection order.
    const itemMap = new Map<string, DOLookupItem>();
    for (const r of results) itemMap.set(r.order_number, r);
    for (const r of draftItems) if (!itemMap.has(r.order_number)) itemMap.set(r.order_number, r);
    const orderedItems = orderNumbers
      .map((n) => itemMap.get(n))
      .filter((x): x is DOLookupItem => Boolean(x));
    onChange(orderNumbers, orderedItems);
    setOpen(false);
  };

  const removeChip = (v: string) => {
    onChange(value.filter((x) => x !== v));
  };

  const selectionCount = useMemo(() => draftSelected.size, [draftSelected]);

  return (
    <div className="space-y-2" id={id}>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs text-secondary-foreground"
            >
              <span className="truncate max-w-[200px]">{v}</span>
              {!disabled && (
                <button
                  type="button"
                  className="opacity-60 hover:opacity-100"
                  onClick={() => removeChip(v)}
                  aria-label={`Remove ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <Search className="h-4 w-4 mr-2" />
        {value.length > 0 ? 'Edit selection' : 'Search & select delivery orders'}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Select delivery orders</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="do-period">Period</Label>
              <PeriodPicker value={period} onChange={setPeriod} />
              <p className="text-xs text-muted-foreground">
                Pick a year, month, or exact day range using the calendar
                button.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="do-product">Product code</Label>
                <Input
                  id="do-product"
                  value={productCode}
                  onChange={(e) => setProductCode(e.target.value)}
                  placeholder="e.g. SRTWC12345"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="do-customer">Customer (debtor)</Label>
                <Input
                  id="do-customer"
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  placeholder="Customer or debtor name"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button type="button" size="sm" onClick={runSearch} disabled={loading}>
                <Search className="h-4 w-4 mr-2" />
                {loading ? 'Searching…' : 'Search'}
              </Button>
            </div>
            <div className="max-h-[320px] overflow-auto rounded-md border border-border">
              {loading ? (
                <p className="p-4 text-sm text-muted-foreground">Searching…</p>
              ) : error ? (
                <p className="p-4 text-sm text-destructive">{error}</p>
              ) : results.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">
                  No delivery orders match these filters.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {results.map((row) => {
                    const checked = draftSelected.has(row.order_number);
                    return (
                      <li
                        key={row.order_number}
                        className="flex items-start gap-3 px-3 py-2 hover:bg-accent/40 cursor-pointer"
                        onClick={() => toggleRow(row)}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggleRow(row)}
                          aria-label={`Select ${row.order_number}`}
                          className="mt-1"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">{row.order_number}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {[
                              row.debtor_name,
                              row.customer_name,
                              row.order_date
                                ? new Date(row.order_date).toLocaleDateString(undefined, {
                                    dateStyle: 'medium',
                                  })
                                : null,
                            ]
                              .filter(Boolean)
                              .join(' • ')}
                          </p>
                          {row.products.length > 0 && (
                            <p className="text-xs text-muted-foreground truncate">
                              {row.products.join(', ')}
                            </p>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {selectionCount} selected
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={handleApply}>
              Add selected
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
