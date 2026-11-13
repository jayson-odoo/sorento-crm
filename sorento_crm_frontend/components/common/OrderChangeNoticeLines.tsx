'use client';

/**
 * The line table of the order change notice form (OCN-ORDER-CHANGE-NOTICE A6): one catalogue
 * product per row, before and after quantities and dates, the delivered quantity and a remark.
 * Built like `SampleRequestLines` on the same `ProductPickCell`: the product search only lists,
 * a click picks, and there is no free-text product. Quantities are never capped by stock.
 * `readOnly` draws the same table as plain values (the detail page).
 */

import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DatePickerField } from '@/components/ui/date-picker';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { ProductPickCell, ProductPickMissed, useProductPickSearch } from '@/components/common/ProductPickCell';
import { formatDateInMalaysia } from '@/lib/helpers';
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
  onChange?: (lines: OcnDraftLine[]) => void;
  search?: (q: string) => Promise<OcnProductHit[]>;
  /** Plain values, no controls: the detail page's table. */
  readOnly?: boolean;
  /** `lines` for the table as a whole; `qty_before_<key>` and the like for one box. */
  errors?: Record<string, string>;
  disabled?: boolean;
}

const QTY_FIELDS = [
  ['qty_before', 'Qty before'],
  ['qty_after', 'Qty after'],
] as const;

const NO_SEARCH = async (): Promise<OcnProductHit[]> => [];
const day = (v: string | null) => (v ? formatDateInMalaysia(v) : '-');

export function OrderChangeNoticeLines({
  lines,
  onChange = () => {},
  search = NO_SEARCH,
  readOnly = false,
  errors = {},
  disabled,
}: OrderChangeNoticeLinesProps) {
  const { fetchProducts, missed, clearMissed } = useProductPickSearch(search);

  const patchLine = (key: string, patch: Partial<OcnDraftLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  if (readOnly) {
    return (
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[760px] table-fixed text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-[26%] px-2 py-2 text-left">Product</th>
              <th className="px-2 py-2 text-left">Qty before</th>
              <th className="px-2 py-2 text-left">Qty after</th>
              <th className="px-2 py-2 text-left">Date before</th>
              <th className="px-2 py-2 text-left">Date after</th>
              <th className="px-2 py-2 text-left">Delivered</th>
              <th className="w-[20%] px-2 py-2 text-left">Remark</th>
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 ? (
              <tr className="border-t">
                <td colSpan={7} className="px-2 py-6 text-center text-muted-foreground">
                  No line items yet
                </td>
              </tr>
            ) : (
              lines.map((line) => (
                <tr key={line.key} data-testid="order-change-notice-line" className="border-t align-top">
                  <td className="truncate px-2 py-2" title={line.label}>
                    {line.label || '-'}
                  </td>
                  <td className="px-2 py-2 tabular-nums">{line.qty_before || '-'}</td>
                  <td className="px-2 py-2 tabular-nums">{line.qty_after || '-'}</td>
                  <td className="px-2 py-2 tabular-nums">{day(line.date_before)}</td>
                  <td className="px-2 py-2 tabular-nums">{day(line.date_after)}</td>
                  <td className="px-2 py-2 tabular-nums">{line.delivered_qty || '-'}</td>
                  <td className="break-words px-2 py-2">{line.remark || '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      {/* The form card is about 853 px at 1280: the columns add up to 840 (Remark takes the rest,
          at least 120), so nothing scrolls sideways on a desktop; a phone scrolls the table in this
          wrapper, never the page (SampleRequestLines). A date cell holds "DD/MM/YYYY" beside the
          34 px calendar button through the picker's own compact props (text-xs, gap-1). */}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[840px] table-fixed text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-8 px-1 py-2 text-left">No.</th>
              <th className="w-[9.25rem] px-1 py-2 text-left">Item Code</th>
              <th className="w-16 px-1 py-2 text-left">Qty before</th>
              <th className="w-16 px-1 py-2 text-left">Qty after</th>
              <th className="w-[9.25rem] px-1 py-2 text-left">Date before</th>
              <th className="w-[9.25rem] px-1 py-2 text-left">Date after</th>
              <th className="w-[4.75rem] px-1 py-2 text-left">Delivered</th>
              <th className="min-w-[7.5rem] px-1 py-2 text-left">Remark</th>
              <th className="w-10 px-0.5 py-2">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => (
              <tr key={line.key} data-testid="order-change-notice-line" className="border-t align-top">
                <td className="px-1 py-2 text-muted-foreground">{index + 1}</td>
                {/* The input clips a long picked name; the cell's title shows it whole. */}
                <td className="px-1 py-2" title={line.label || undefined}>
                  <ProductPickCell<OcnProductHit>
                    productId={line.product_id}
                    label={line.label}
                    disabled={disabled}
                    fetchProducts={fetchProducts}
                    onPick={(item, label) => {
                      clearMissed();
                      patchLine(line.key, item ? { product_id: item.id, label } : { product_id: '', label: '' });
                    }}
                  />
                  {errors[`product_${line.key}`] && (
                    <p className="mt-1 text-xs text-destructive">{errors[`product_${line.key}`]}</p>
                  )}
                </td>
                {QTY_FIELDS.map(([field, caption]) => (
                  <td key={field} className="px-1 py-2">
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
                <td className="px-1 py-2">
                  <DatePickerField
                    ariaLabel="Date before"
                    className="gap-1"
                    inputClassName="px-2 text-xs"
                    disabled={disabled}
                    value={line.date_before}
                    onChange={(v) => patchLine(line.key, { date_before: v })}
                  />
                </td>
                <td className="px-1 py-2">
                  <DatePickerField
                    ariaLabel="Date after"
                    className="gap-1"
                    inputClassName="px-2 text-xs"
                    disabled={disabled}
                    value={line.date_after}
                    onChange={(v) => patchLine(line.key, { date_after: v })}
                  />
                </td>
                <td className="px-1 py-2">
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
                <td className="px-1 py-2">
                  <Input
                    aria-label="Remark"
                    disabled={disabled}
                    value={line.remark}
                    onChange={(e) => patchLine(line.key, { remark: e.target.value })}
                  />
                </td>
                <td className="px-0.5 py-2">
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
      <ProductPickMissed text={missed} hint="Pick the product you mean." />
      {errors.lines && <p className="mt-2 text-xs text-destructive">{errors.lines}</p>}
    </div>
  );
}
