'use client';

/**
 * The product table of a new product application (NEW-PRODUCT-APP v5): ONE table, one row per
 * product, like the purchase request and sample request lines. Staff and portal use this one
 * component so the two cannot drift. `readOnly` shows plain text in place of the inputs (same
 * columns, same order); `showCost` adds purchasing's Cost (MYR) (`costEditable` makes it an input
 * for purchasing); `renderOpenedAs` adds the staff "Opened as" column. The table scrolls
 * sideways inside its own box (phone width); the page never does.
 */

import type { ReactNode } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { blankLine, type DraftLine } from '@/lib/new-product-application-form';

export type LookupFetcher = (
  query: string,
  pageIndex: number,
) => Promise<SearchableSelectOption[]>;

export interface NewProductApplicationLinesProps {
  lines: DraftLine[];
  onChange: (next: DraftLine[]) => void;
  brands: LookupFetcher;
  /** Keys are `expected_qty_<line key>` plus `lines`. */
  errors?: Record<string, string>;
  readOnly?: boolean;
  /** Adds the Cost (MYR) column (purchasing feedback). */
  showCost?: boolean;
  /** With `showCost`: one input per row, named "Cost for product N". */
  costEditable?: boolean;
  /** Adds the "Opened as" column; the host draws what goes in it. */
  renderOpenedAs?: (line: DraftLine, index: number) => ReactNode;
}

const dash = (v: string | null | undefined) => (v && v.trim() ? v : '-');
const TH = 'px-2 py-2 text-left font-medium';
const TD = 'px-2 py-2 align-top';

export function NewProductApplicationLines({
  lines,
  onChange,
  brands,
  errors = {},
  readOnly,
  showCost,
  costEditable,
  renderOpenedAs,
}: NewProductApplicationLinesProps) {
  const patch = (key: string, next: Partial<DraftLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...next } : l)));

  const text = (
    line: DraftLine,
    field:
      | 'proposed_code'
      | 'description'
      | 'dimension'
      | 'material'
      | 'thickness'
      | 'packing',
    label: string,
  ) =>
    readOnly ? (
      <div className="truncate" title={line[field]}>
        {dash(line[field])}
      </div>
    ) : (
      <Input
        aria-label={label}
        className="h-8"
        value={line[field]}
        onChange={(e) => patch(line.key, { [field]: e.target.value })}
      />
    );

  const minWidth = 900 + (showCost ? 120 : 0) + (renderOpenedAs ? 300 : 0);

  return (
    <div className="space-y-3">
      <div className="relative overflow-x-auto">
        <table className="w-full table-fixed text-sm" style={{ minWidth }}>
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className={`${TH} w-14`}>No.</th>
              <th className={`${TH} w-36`}>Product code</th>
              <th className={`${TH} w-52`}>Product type *</th>
              <th className={`${TH} w-32`}>Dimension</th>
              <th className={`${TH} w-32`}>Material</th>
              <th className={`${TH} w-24`}>Thickness</th>
              <th className={`${TH} w-28`}>Packing</th>
              <th className={`${TH} w-40`}>Brand</th>
              <th className={`${TH} w-24`}>Qty</th>
              {showCost && <th className={`${TH} w-28`}>Cost (MYR)</th>}
              {renderOpenedAs && <th className={`${TH} w-72`}>Opened as</th>}
              {!readOnly && (
                <th className="w-12 px-2 py-2">
                  <span className="sr-only">Remove</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => (
              <tr key={line.key} data-testid="npa-line" className="border-t">
                <td className={`${TD} text-muted-foreground`}>{index + 1}</td>
                <td className={TD}>
                  {text(line, 'proposed_code', 'Product code')}
                </td>
                <td className={TD}>
                  {text(line, 'description', 'Product type')}
                </td>
                <td className={TD}>{text(line, 'dimension', 'Dimension')}</td>
                <td className={TD}>{text(line, 'material', 'Material')}</td>
                <td className={TD}>{text(line, 'thickness', 'Thickness')}</td>
                <td className={TD}>{text(line, 'packing', 'Packing')}</td>
                <td className={TD}>
                  {readOnly ? (
                    <div className="truncate" title={line.brand_label}>
                      {dash(line.brand_label)}
                    </div>
                  ) : (
                    <SearchableSelect
                      aria-label="Brand"
                      value={line.brand_id}
                      clearable
                      truncateTriggerLabel
                      wrapOptions
                      placeholder="Search brand"
                      fetchOptions={brands}
                      selectedOption={
                        line.brand_id
                          ? { value: line.brand_id, label: line.brand_label }
                          : undefined
                      }
                      onChange={(v) => {
                        if (!v)
                          patch(line.key, { brand_id: '', brand_label: '' });
                      }}
                      onOptionChange={(opt) =>
                        opt &&
                        patch(line.key, {
                          brand_id: opt.value,
                          brand_label: opt.label,
                        })
                      }
                    />
                  )}
                </td>
                <td className={TD}>
                  {readOnly ? (
                    dash(line.expected_qty)
                  ) : (
                    <NumberInput
                      inputMode="decimal"
                      step="any"
                      aria-label="Qty"
                      className="h-8"
                      value={line.expected_qty}
                      error={errors[`expected_qty_${line.key}`]}
                      onChange={(e) =>
                        patch(line.key, { expected_qty: e.target.value })
                      }
                    />
                  )}
                </td>
                {showCost && (
                  <td className={TD}>
                    {costEditable ? (
                      <NumberInput
                        inputMode="decimal"
                        step="any"
                        aria-label={`Cost for product ${index + 1}`}
                        className="h-8"
                        value={line.cost_price}
                        onChange={(e) =>
                          patch(line.key, { cost_price: e.target.value })
                        }
                      />
                    ) : line.cost_price.trim() ? (
                      `MYR ${line.cost_price}`
                    ) : (
                      '-'
                    )}
                  </td>
                )}
                {renderOpenedAs && (
                  <td className={TD}>{renderOpenedAs(line, index)}</td>
                )}
                {!readOnly && (
                  <td className={TD}>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove row ${index + 1}`}
                      onClick={() =>
                        onChange(lines.filter((l) => l.key !== line.key))
                      }
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {errors.lines && (
        <p className="text-xs text-destructive">{errors.lines}</p>
      )}
      {!readOnly && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...lines, blankLine()])}
        >
          <Plus className="size-4" />
          Add row
        </Button>
      )}
    </div>
  );
}
