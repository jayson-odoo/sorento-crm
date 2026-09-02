'use client';

import { useQuery } from '@tanstack/react-query';
import { getSpecRegistry } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';

/** Every hook and mutation that touches the registry list shares this key. */
export const SPEC_REGISTRY_QUERY_KEY = ['spec-registry'];

/**
 * The whole registry, cached the way the ETag it rides implies: 37 rows, read once
 * and reused rather than refetched on every render (D9). The record page selects
 * one row out of this same cache instead of a GET of its own.
 */
export function useSpecRegistryQuery() {
  return useQuery({
    queryKey: SPEC_REGISTRY_QUERY_KEY,
    queryFn: () => getSpecRegistry(),
    select: (data) => data.keys,
    staleTime: 60_000,
  });
}

/**
 * One key out of the cached list, by its slug.
 *
 * No single-key GET exists (D9): the record page reads this list and selects out
 * of it, so a key that is not in `keys` (a bad URL, a key deleted since) comes back
 * `undefined` rather than a 404 of its own.
 */
export function selectSpecKey(
  keys: SpecRegistryKey[] | undefined,
  specKey: string,
): SpecRegistryKey | undefined {
  return keys?.find((key) => key.spec_key === specKey);
}
