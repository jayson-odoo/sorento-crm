import type { ProductSpecKey } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * The registry list's own text filter, sorted by label (AC-A.2) - shared by the grid
 * and by the record page's pager (B.1, D9), so a search that narrowed the list the
 * reader came from narrows the pager's position the same way. `productKeys` is the
 * grid's product-code narrowing, applied when non-null; it is UI-local state (the
 * debounced probe result) so the pager, which only carries the plain text query in
 * the URL, walks the plain-text-filtered set rather than a product narrowing it
 * cannot reconstruct from the URL alone.
 */
export function filterSpecKeys(
  keys: SpecRegistryKey[],
  filter: string,
  productKeys?: Record<string, ProductSpecKey> | null,
): SpecRegistryKey[] {
  const needle = filter.trim().toLowerCase();
  const filtered = !needle
    ? keys
    : keys.filter((key) => {
        if (productKeys) return key.spec_key in productKeys;
        const words = Object.entries(key.synonyms ?? {}).flatMap(([value, list]) => [
          value,
          ...list,
        ]);
        return [key.spec_key, key.label, ...key.allowed_values, ...words]
          .join(' ')
          .toLowerCase()
          .includes(needle);
      });
  return [...filtered].sort((a, b) => a.label.localeCompare(b.label));
}
