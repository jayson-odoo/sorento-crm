'use client';

import * as React from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
// The shared products `/select` mapper. Its name says "variant" because that screen needed
// it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';

/**
 * Our code, hiding inside theirs, as a search term.
 *
 * `BUI-HB-SRTWB7055` is `SRTWB7055` with the customer's prefix bolted on, so typing the whole
 * printed code into a product search returns nothing and the picker opens on "No products
 * match". The backend resolver already knows this (`_code_candidates`: the code plus every
 * dash-suffix of it), and the shortest suffix still worth searching is the one to seed with,
 * because a search is a substring match and the shortest candidate casts the widest net.
 * Four characters is the same floor the backend's own fuzzy probe uses, and it is what keeps
 * the trailing `-RL` of `BUI-HB-SRTWC8613-RL` from being mistaken for the code.
 */
export function productSearchSeed(customerCode: string | null): string {
  const cleaned = (customerCode ?? '').trim();
  if (!cleaned) return '';
  const parts = cleaned.split('-');
  for (let start = parts.length - 1; start >= 1; start -= 1) {
    const suffix = parts.slice(start).join('-');
    if (suffix.length >= 4) return suffix;
  }
  return cleaned;
}

/**
 * Identifies, or corrects, the product a schedule column means.
 *
 * Offered in three places for one reason: the reviewer has to be able to fix a column from
 * wherever they read that it is broken. In the matrix it sits in the column header, on a
 * phone inside the card, and in the reconciliation list beside the sentence that named the
 * problem, which is where most people meet it first.
 */
export function DeliveryScheduleProductPicker({
  idPrefix,
  columnIndex,
  customerCode,
  action = 'Pick the product',
  variant = 'field',
  disabled,
  onPick,
}: {
  /**
   * The matrix, the phone view and the reconciliation list are all mounted at once (they
   * differ by breakpoint or by section, not by state), so the element id has to say which
   * one this is or they collide in one document.
   */
  idPrefix: string;
  columnIndex: number;
  customerCode: string | null;
  /**
   * What pressing this does, in the user's words. A column with no product at all is being
   * picked for the first time; a column that resolved to the wrong product is being changed.
   */
  action?: string;
  /** `field` is a select box; `compact` is a small text button for a place with no room. */
  variant?: 'field' | 'compact';
  disabled?: boolean;
  onPick: (productId: string) => void;
}) {
  const fetchProducts = React.useCallback(async (query: string) => {
    const rows = await getProductsForVariantSelect(query || undefined);
    return rows.map((row) => ({
      value: row.id,
      label: row.product_code,
      description: row.product_name,
    }));
  }, []);

  const id = `${idPrefix}-column-product-${columnIndex}`;
  const name = customerCode
    ? `${action} for ${customerCode}`
    : `${action} for column ${columnIndex + 1}`;
  const seed = productSearchSeed(customerCode);

  if (variant === 'compact') {
    return (
      <SearchableSelect
        value=""
        onChange={onPick}
        disabled={disabled}
        fetchOptions={fetchProducts}
        initialQuery={seed}
        emptyMessage="No products match"
        className="min-w-[280px]"
        renderTrigger={({ disabled: isDisabled }) => (
          <button
            type="button"
            id={id}
            disabled={isDisabled}
            aria-label={name}
            className={cn(
              'rounded-sm text-start text-[11px] font-normal text-primary underline-offset-2',
              'hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary',
              'disabled:cursor-not-allowed disabled:text-muted-foreground',
            )}
          >
            {action}
          </button>
        )}
      />
    );
  }

  return (
    <>
      <label htmlFor={id} className="sr-only">
        {name}
      </label>
      <SearchableSelect
        id={id}
        value=""
        onChange={onPick}
        size="sm"
        disabled={disabled}
        fetchOptions={fetchProducts}
        initialQuery={seed}
        placeholder={action}
        emptyMessage="No products match"
        triggerClassName="w-full"
        className="min-w-[280px]"
      />
    </>
  );
}
