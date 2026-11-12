'use client';

/**
 * The line table of the sample request form, shared by the staff page and the portal so the two
 * cannot drift: row 1 is the sample board (a tick and its label, never a product), then one row
 * per product with its own product search. Search lists; only a click on a hit picks.
 */

import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { ProductPickCell, ProductPickMissed, useProductPickSearch } from '@/components/common/ProductPickCell';
import { numberFieldError } from '@/lib/number-field';
import { WHOLE_AT_LEAST_ONE, type DraftLine, type FormState } from '@/lib/sample-request-form';
import type { SampleRequestProductHit } from '@/types/sampleRequest';

export interface SampleRequestLinesProps {
  value: Pick<FormState, 'lines' | 'board_mounting' | 'board_label'>;
  onChange: (patch: Partial<Pick<FormState, 'lines' | 'board_mounting' | 'board_label'>>) => void;
  search: (q: string) => Promise<SampleRequestProductHit[]>;
  /** Ask the search even with an empty box: a request from a quotation lists that quotation's
   * products on tap (SFQ-27), where the whole catalogue is searched only by typing. */
  listWhenEmpty?: boolean;
  /** Column captions differ between the staff page and the portal. */
  captions: { no: string; item: string; qty: string };
  errors?: Record<string, string>;
  disabled?: boolean;
}

export function SampleRequestLines({
  value,
  onChange,
  search,
  listWhenEmpty = false,
  captions,
  errors = {},
  disabled,
}: SampleRequestLinesProps) {
  // The search text the server last answered with nothing for; the empty message names it.
  const { fetchProducts, missed, clearMissed } = useProductPickSearch(search, listWhenEmpty);

  const patchLine = (key: string, patch: Partial<DraftLine>) =>
    onChange({ lines: value.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) });

  const firstProductRow = value.board_mounting ? 2 : 1;

  return (
    <div>
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[560px] table-fixed text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-12 px-2 py-2 text-left">{captions.no}</th>
              <th className="w-[44%] px-2 py-2 text-left">{captions.item}</th>
              <th className="w-20 px-2 py-2 text-left">{captions.qty}</th>
              <th className="px-2 py-2 text-left">Remark</th>
              <th className="w-10 px-2 py-2">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t align-top">
              <td className="px-2 py-2 text-muted-foreground">1</td>
              <td className="px-2 py-2" colSpan={4}>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="sr-board"
                      checked={value.board_mounting}
                      disabled={disabled}
                      onCheckedChange={(on) => onChange({ board_mounting: on === true })}
                    />
                    <Label htmlFor="sr-board">Mount &amp; label sample board</Label>
                  </div>
                  {value.board_mounting && (
                    <div className="min-w-[12rem] flex-1">
                      <Input
                        aria-label="Board label"
                        placeholder="Board label"
                        disabled={disabled}
                        value={value.board_label}
                        onChange={(e) => onChange({ board_label: e.target.value })}
                      />
                    </div>
                  )}
                </div>
                {errors.board_label && (
                  <p className="mt-1 text-xs text-destructive">{errors.board_label}</p>
                )}
              </td>
            </tr>
            {value.lines.map((line, index) => (
              <tr key={line.key} data-testid="sample-request-line" className="border-t align-top">
                <td className="px-2 py-2 text-muted-foreground">{firstProductRow + index}</td>
                <td className="px-2 py-2">
                  <ProductPickCell<SampleRequestProductHit>
                    productId={line.product_id}
                    label={line.label}
                    disabled={disabled}
                    fetchProducts={fetchProducts}
                    onPick={(item, label) => {
                      clearMissed();
                      patchLine(
                        line.key,
                        item
                          ? { product_id: item.id, label, inactive: false }
                          : { product_id: '', label: '' },
                      );
                    }}
                  />
                  {line.inactive && (
                    <span className="block text-xs text-muted-foreground">Inactive</span>
                  )}
                </td>
                <td className="px-2 py-2">
                  <NumberInput
                    inputMode="numeric"
                    min={1}
                    aria-label="Quantity"
                    disabled={disabled}
                    value={line.qty}
                    error={errors[`qty_${line.key}`] ? numberFieldError(line.qty, WHOLE_AT_LEAST_ONE) : undefined}
                    onChange={(e) => patchLine(line.key, { qty: e.target.value })}
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
                      onClick={() =>
                        onChange({ lines: value.lines.filter((l) => l.key !== line.key) })
                      }
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
      <ProductPickMissed
        text={missed}
        hint="Pick the product you mean, or ask purchasing to add it as a new product before you request it."
      />
      {errors.lines && <p className="mt-2 text-xs text-destructive">{errors.lines}</p>}
    </div>
  );
}
