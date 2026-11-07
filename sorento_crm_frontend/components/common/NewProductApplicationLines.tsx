'use client';

/**
 * The product table of a new product application (NEW-PRODUCT-APP v5): ONE table, one row per
 * product, like the purchase request and sample request lines. Staff and portal use this one
 * component so the two cannot drift. `readOnly` shows plain text in place of the inputs (same
 * columns, same order); `showCost` adds purchasing's Cost (MYR) (`costEditable` makes it an input
 * for purchasing); `renderOpenedAs` adds the staff "Opened as" column. The table scrolls
 * sideways inside its own box (phone width); the page never does.
 */

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Info, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import {
  blankLine,
  currentIdsKey,
  type DraftLine,
} from '@/lib/new-product-application-form';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { NewProductApplicationSuggestion } from '@/types/newProductApplication';

export type LookupFetcher = (
  query: string,
  pageIndex: number,
) => Promise<SearchableSelectOption[]>;

export type ProductFetcher = (
  query: string,
  pageIndex: number,
) => Promise<SearchableMultiSelectOption[]>;

export interface NewProductApplicationLinesProps {
  lines: DraftLine[];
  onChange: (next: DraftLine[]) => void;
  brands: LookupFetcher;
  /** Catalogue codes for the Product code cell (value = product id, label = code). */
  products: ProductFetcher;
  /** Earlier codes made from exactly these current codes; asked again when the pick changes. */
  reuse?: (productIds: string[]) => Promise<NewProductApplicationSuggestion[]>;
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

const SUGGESTION_DEBOUNCE_MS = 300;
const MAX_SUGGESTIONS = 3;

/** One earlier code, as a sentence. The portal carries no application number. */
function suggestionText(
  s: NewProductApplicationSuggestion,
  fromCodes: string,
): ReactNode {
  const parts = [
    s.application_no,
    s.created_at ? formatDateInMalaysia(s.created_at) : '',
    s.description ? `"${s.description}"` : '',
  ].filter(Boolean);
  return (
    <>
      A code was already created from {fromCodes}: <b>{s.product_code}</b>
      {parts.length ? ` (${parts.join(', ')})` : ''}
    </>
  );
}

/** The information row under a line whose current codes were used before. Nothing is applied. */
function SuggestionRow({
  line,
  reuse,
  colSpan,
}: {
  line: DraftLine;
  reuse?: NewProductApplicationLinesProps['reuse'];
  colSpan: number;
}) {
  const key = currentIdsKey(line.current_products.map((p) => p.id));
  const [fetched, setFetched] = useState<{
    key: string;
    list: NewProductApplicationSuggestion[];
  } | null>(null);

  useEffect(() => {
    if (!reuse || !key || key === line.suggestions_for) return;
    let live = true;
    const timer = setTimeout(() => {
      reuse(key.split(','))
        .then((list) => live && setFetched({ key, list }))
        .catch(() => live && setFetched({ key, list: [] }));
    }, SUGGESTION_DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [key, reuse, line.suggestions_for]);

  const list = !key
    ? []
    : key === line.suggestions_for
      ? line.suggestions
      : fetched?.key === key
        ? fetched.list
        : [];
  if (list.length === 0) return null;
  const fromCodes = line.current_products.map((p) => p.product_code).join(', ');
  return (
    <tr data-testid="npa-line-suggestions">
      <td colSpan={colSpan} className="px-2 pb-2">
        <ul className="space-y-1 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          {list.slice(0, MAX_SUGGESTIONS).map((s) => (
            <li
              key={`${s.product_id}-${s.application_no ?? s.created_at}`}
              className="flex gap-2"
            >
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span className="min-w-0 break-words">
                {suggestionText(s, fromCodes)}
              </span>
            </li>
          ))}
        </ul>
      </td>
    </tr>
  );
}

export function NewProductApplicationLines({
  lines,
  onChange,
  brands,
  products,
  reuse,
  errors = {},
  readOnly,
  showCost,
  costEditable,
  renderOpenedAs,
}: NewProductApplicationLinesProps) {
  const patch = (key: string, next: Partial<DraftLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...next } : l)));

  // The picker hands back ids only, so remember the code of every option it has shown.
  const known = useRef(new Map<string, string>());
  const fetchProducts = useMemo<ProductFetcher>(
    () => async (q, page) => {
      const options = await products(q, page);
      for (const o of options) known.current.set(o.value, o.label);
      return options;
    },
    [products],
  );

  const codesCell = (line: DraftLine) => {
    const joined = line.current_products.map((p) => p.product_code).join(', ');
    return (
      <div className="min-w-0 space-y-1">
        {readOnly ? (
          <div className="truncate" title={joined}>
            {dash(joined)}
          </div>
        ) : (
          <SearchableMultiSelect
            aria-label="Product code"
            value={line.current_products.map((p) => p.id)}
            clearable
            wrapOptions
            placeholder="Search product code"
            emptyMessage="No product matches that."
            fetchOptions={fetchProducts}
            selectedOptions={line.current_products.map((p) => ({
              value: p.id,
              label: p.product_code,
            }))}
            onChange={(ids) =>
              patch(line.key, {
                current_products: ids.map((id) => ({
                  id,
                  product_code:
                    line.current_products.find((p) => p.id === id)
                      ?.product_code ??
                    known.current.get(id) ??
                    id,
                })),
              })
            }
          />
        )}
        {line.inquiry_code_hint && line.current_products.length === 0 && (
          <p className="break-words text-xs text-muted-foreground">
            Inquiry asked: &quot;{line.inquiry_code_hint}&quot;
          </p>
        )}
      </div>
    );
  };

  const text = (
    line: DraftLine,
    field: 'description' | 'dimension' | 'material' | 'thickness' | 'packing',
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

  const minWidth = 960 + (showCost ? 120 : 0) + (renderOpenedAs ? 300 : 0);
  const columnCount =
    9 + (showCost ? 1 : 0) + (renderOpenedAs ? 1 : 0) + (readOnly ? 0 : 1);

  return (
    <div className="space-y-3">
      <div className="relative overflow-x-auto">
        <table className="w-full table-fixed text-sm" style={{ minWidth }}>
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className={`${TH} w-14`}>No.</th>
              <th className={`${TH} w-48`}>Product code</th>
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
              <Fragment key={line.key}>
                <tr data-testid="npa-line" className="border-t">
                  <td className={`${TD} text-muted-foreground`}>{index + 1}</td>
                  <td className={TD}>{codesCell(line)}</td>
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
                <SuggestionRow
                  line={line}
                  reuse={reuse}
                  colSpan={columnCount}
                />
              </Fragment>
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
