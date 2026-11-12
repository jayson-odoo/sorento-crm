'use client';

/**
 * The line table of the order change notice form (OCN-ORDER-CHANGE-NOTICE A6): one catalogue
 * product per row, before and after quantities and dates, the delivered quantity and a remark.
 * Built like `SampleRequestLines`: the product search only lists, a click picks, and there is no
 * free-text product. Quantities are never capped by stock.
 */

import { useCallback, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DatePickerField } from '@/components/ui/date-picker';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { codeWithName } from '@/lib/product-display';
import type { OcnProductHit } from '@/types/orderChangeNotice';

export interface OcnDraftLine {
  /** Client-side row key. */
  key: string;
  product_id: string;
  /** The picked product as shown, "code name". */
  label: string;
  qty_before: string;
  qty_after: string;
  date_before: string | null;
  date_after: string | null;
  delivered_qty: string;
  remark: string;
}

let nextKey = 0;
export function blankOcnLine(): OcnDraftLine {
  nextKey += 1;
  return {
    key: `ocn-line-${nextKey}`,
    product_id: '',
    label: '',
    qty_before: '',
    qty_after: '',
    date_before: null,
    date_after: null,
    delivered_qty: '',
    remark: '',
  };
}

export interface OrderChangeNoticeLinesProps {
  lines: OcnDraftLine[];
  onChange: (lines: OcnDraftLine[]) => void;
  search: (q: string) => Promise<OcnProductHit[]>;
  /** `lines` for the table as a whole; `qty_before_<key>` and the like for one box. */
  errors?: Record<string, string>;
  disabled?: boolean;
}

const QTY_FIELDS = [
  ['qty_before', 'Qty before'],
  ['qty_after', 'Qty after'],
] as const;

export function OrderChangeNoticeLines({
  lines,
  onChange,
  search,
  errors = {},
  disabled,
}: OrderChangeNoticeLinesProps) {
  const [missed, setMissed] = useState('');

  const fetchProducts = useCallback(
    async (q: string) => {
      if (!q.trim()) return [];
      const hits = await search(q);
      setMissed(hits.length === 0 ? q.trim() : '');
      return hits;
    },
    [search],
  );

  const patchLine = (key: string, patch: Partial<OcnDraftLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  return (
    <div>
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[960px] table-fixed text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-12 px-2 py-2 text-left">No.</th>
              <th className="w-[24%] px-2 py-2 text-left">Item Code</th>
              <th className="w-24 px-2 py-2 text-left">Qty before</th>
              <th className="w-24 px-2 py-2 text-left">Qty after</th>
              <th className="w-40 px-2 py-2 text-left">Date before</th>
              <th className="w-40 px-2 py-2 text-left">Date after</th>
              <th className="w-24 px-2 py-2 text-left">Delivered</th>
              <th className="px-2 py-2 text-left">Remark</th>
              <th className="w-10 px-2 py-2">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => (
              <tr key={line.key} data-testid="order-change-notice-line" className="border-t align-top">
                <td className="px-2 py-2 text-muted-foreground">{index + 1}</td>
                <td className="px-2 py-2">
                  <AsyncCombobox<OcnProductHit>
                    ariaLabel="Item code"
                    value={line.product_id}
                    displayValue={line.label}
                    disabled={disabled}
                    allowFreeText={false}
                    fetchOptions={fetchProducts}
                    optionValue={(o) => o.id}
                    optionLabel={(o) => codeWithName(o.product_code, o.product_name)}
                    optionMeta={(o) => o.brand_name ?? ''}
                    placeholder="Search item code"
                    onChange={(v, item) => {
                      setMissed('');
                      patchLine(
                        line.key,
                        item
                          ? { product_id: v, label: codeWithName(item.product_code, item.product_name) }
                          : { product_id: '', label: '' },
                      );
                    }}
                  />
                  {errors[`product_${line.key}`] && (
                    <p className="mt-1 text-xs text-destructive">{errors[`product_${line.key}`]}</p>
                  )}
                </td>
                {QTY_FIELDS.map(([field, caption]) => (
                  <td key={field} className="px-2 py-2">
                    <NumberInput
                      inputMode="decimal"
                      min={0}
                      aria-label={caption}
                      disabled={disabled}
                      value={line[field]}
                      error={errors[`${field}_${line.key}`]}
                      onChange={(e) => patchLine(line.key, { [field]: e.target.value })}
                    />
                  </td>
                ))}
                <td className="px-2 py-2">
                  <DatePickerField
                    ariaLabel="Date before"
                    disabled={disabled}
                    value={line.date_before}
                    onChange={(v) => patchLine(line.key, { date_before: v })}
                  />
                </td>
                <td className="px-2 py-2">
                  <DatePickerField
                    ariaLabel="Date after"
                    disabled={disabled}
                    value={line.date_after}
                    onChange={(v) => patchLine(line.key, { date_after: v })}
                  />
                </td>
                <td className="px-2 py-2">
                  <NumberInput
                    inputMode="decimal"
                    min={0}
                    aria-label="Delivered"
                    disabled={disabled}
                    value={line.delivered_qty}
                    error={errors[`delivered_qty_${line.key}`]}
                    onChange={(e) => patchLine(line.key, { delivered_qty: e.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  <Input
                    aria-label="Remark"
                    disabled={disabled}
                    value={line.remark}
                    onChange={(e) => patchLine(line.key, { remark: e.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  {!disabled && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label="Remove line"
                      onClick={() => onChange(lines.filter((l) => l.key !== line.key))}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {missed && (
        <p className="mt-2 text-sm text-muted-foreground">
          {missed} is not in the product list. Pick the product you mean.
        </p>
      )}
      {errors.lines && <p className="mt-2 text-xs text-destructive">{errors.lines}</p>}
    </div>
  );
}
