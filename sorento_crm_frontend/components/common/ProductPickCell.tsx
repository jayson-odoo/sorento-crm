'use client';

/**
 * The catalogue product picker of a form's line table, shared by the sample request lines and
 * the order change notice lines: the search only lists, a click picks, and there is no free-text
 * product. `useProductPickSearch` remembers the text the catalogue had nothing for, so the table
 * can say so once under itself (`ProductPickMissed`).
 */

import { useCallback, useState } from 'react';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { codeWithName } from '@/lib/product-display';

export interface ProductPickHit {
  id: string;
  product_code: string;
  product_name: string;
  brand_name?: string | null;
}

export function useProductPickSearch<T extends ProductPickHit>(
  search: (q: string) => Promise<T[]>,
  listWhenEmpty = false,
) {
  const [missed, setMissed] = useState('');
  const fetchProducts = useCallback(
    async (q: string) => {
      if (!q.trim() && !listWhenEmpty) return [];
      const hits = await search(q);
      setMissed(hits.length === 0 ? q.trim() : '');
      return hits;
    },
    [search, listWhenEmpty],
  );
  const clearMissed = useCallback(() => setMissed(''), []);
  return { fetchProducts, missed, clearMissed };
}

export function ProductPickCell<T extends ProductPickHit>({
  productId,
  label,
  fetchProducts,
  disabled,
  onPick,
}: {
  productId: string;
  /** The picked product as shown, "code name". */
  label: string;
  fetchProducts: (q: string) => Promise<T[]>;
  disabled?: boolean;
  /** The picked product, or null when the box is cleared. */
  onPick: (hit: T | null, label: string) => void;
}) {
  return (
    <AsyncCombobox<T>
      ariaLabel="Item code"
      value={productId}
      displayValue={label}
      disabled={disabled}
      allowFreeText={false}
      fetchOptions={fetchProducts}
      optionValue={(o) => o.id}
      optionLabel={(o) => codeWithName(o.product_code, o.product_name)}
      optionMeta={(o) => o.brand_name ?? ''}
      placeholder="Search item code"
      onChange={(_v, item) =>
        onPick(item ?? null, item ? codeWithName(item.product_code, item.product_name) : '')
      }
    />
  );
}

/** The one line under a table when the catalogue had nothing for the typed text. */
export function ProductPickMissed({ text, hint }: { text: string; hint: string }) {
  if (!text) return null;
  return (
    <p className="mt-2 text-sm text-muted-foreground">
      {text} is not in the product list. {hint}
    </p>
  );
}
