'use client';

/**
 * The PRODUCT CODES header field of a new product application (NPA-FROM-SI): the catalogue codes
 * the application is based on (none = a brand-new item), then what the inquiry asked when that was
 * not one code, then the earlier codes made from exactly this set (information only). Staff and
 * portal share it; `readOnly` shows the codes as comma text.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Info } from 'lucide-react';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { InquiryReadValue } from '@/app/(protected)/procurement-management/stock-inquiries/components/ProductInquiryFormLayout';
import { currentIdsKey, type FormState } from '@/lib/new-product-application-form';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { NewProductApplicationSuggestion } from '@/types/newProductApplication';

export type ProductFetcher = (
  query: string,
  pageIndex: number,
) => Promise<SearchableMultiSelectOption[]>;

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

function Suggestions({
  value,
  reuse,
}: {
  value: FormState;
  reuse?: (productIds: string[]) => Promise<NewProductApplicationSuggestion[]>;
}) {
  const key = currentIdsKey(value.current_products.map((p) => p.id));
  const [fetched, setFetched] = useState<{
    key: string;
    list: NewProductApplicationSuggestion[];
  } | null>(null);

  useEffect(() => {
    if (!reuse || !key || key === value.suggestions_for) return;
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
  }, [key, reuse, value.suggestions_for]);

  const list = !key
    ? []
    : key === value.suggestions_for
      ? value.suggestions
      : fetched?.key === key
        ? fetched.list
        : [];
  if (list.length === 0) return null;
  const fromCodes = value.current_products.map((p) => p.product_code).join(', ');
  return (
    <ul
      data-testid="npa-suggestions"
      className="space-y-1 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900"
    >
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
  );
}

export function NewProductApplicationProductCodes({
  value,
  onChange,
  products,
  reuse,
  readOnly,
}: {
  value: FormState;
  onChange: (next: FormState) => void;
  products: ProductFetcher;
  reuse?: (productIds: string[]) => Promise<NewProductApplicationSuggestion[]>;
  readOnly?: boolean;
}) {
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
  const joined = value.current_products.map((p) => p.product_code).join(', ');

  return (
    <div className="min-w-0 space-y-2">
      {readOnly ? (
        <InquiryReadValue>{joined}</InquiryReadValue>
      ) : (
        <SearchableMultiSelect
          aria-label="Product codes"
          value={value.current_products.map((p) => p.id)}
          clearable
          wrapOptions
          placeholder="Search product code"
          emptyMessage="No product matches that."
          fetchOptions={fetchProducts}
          selectedOptions={value.current_products.map((p) => ({
            value: p.id,
            label: p.product_code,
          }))}
          onChange={(ids) =>
            onChange({
              ...value,
              current_products: ids.map((id) => ({
                id,
                product_code:
                  value.current_products.find((p) => p.id === id)
                    ?.product_code ??
                  known.current.get(id) ??
                  id,
              })),
            })
          }
        />
      )}
      {value.inquiry_code_hint && value.current_products.length === 0 && (
        <p className="break-words text-xs text-muted-foreground">
          Inquiry asked: &quot;{value.inquiry_code_hint}&quot;
        </p>
      )}
      <Suggestions value={value} reuse={reuse} />
    </div>
  );
}
