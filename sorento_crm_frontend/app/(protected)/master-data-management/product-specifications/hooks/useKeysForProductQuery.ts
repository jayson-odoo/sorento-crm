'use client';

import { useEffect, useState } from 'react';
import { getKeysForProduct } from '../services/productSpecService';
import type { ProductSpecKey } from '../services/productSpecService';

export interface KeysForProductResult {
  matchedCode: string | null;
  keys: Record<string, ProductSpecKey> | null;
  loading: boolean;
}

/**
 * Look up which specifications a product code carries, so the registry grid can
 * narrow to it (AC-A.2).
 *
 * Takes the caller's DEBOUNCED value, so this fires once per settled query, not
 * once per keystroke. Only asked of the server when the query looks like a code -
 * at least 3 characters with a digit in it - so a word like "chrome" never leaves
 * the browser.
 */
export function useKeysForProductQuery(debouncedQuery: string): KeysForProductResult {
  const [result, setResult] = useState<Omit<KeysForProductResult, 'loading'>>({
    matchedCode: null,
    keys: null,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (trimmed.length < 3 || !/\d/.test(trimmed)) {
      setResult({ matchedCode: null, keys: null });
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getKeysForProduct(trimmed)
      .then((response) => {
        if (cancelled) return;
        setResult({
          matchedCode: response.matched_product?.product_code ?? null,
          keys: response.matched_product ? response.keys : null,
        });
      })
      .catch(() => {
        if (!cancelled) setResult({ matchedCode: null, keys: null });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  return { ...result, loading };
}
