'use client';

import { useQuery } from '@tanstack/react-query';
import { previewSpecSearch } from '../services/productSpecService';

/**
 * The preview search for one customer phrase (S-15, review round 2), keyed by the
 * phrase. An answer lands under the phrase it was asked for, and the screen reads
 * only the current phrase's key, so a slower answer to an earlier phrase can never
 * overwrite the answer to a later one. The phrase goes out once, as `phrase`; its
 * words ride `free_terms`.
 */
export function useSpecSearchPreviewQuery(phrase: string) {
  const trimmed = phrase.trim();
  return useQuery({
    queryKey: ['spec-search-preview', trimmed],
    queryFn: () =>
      previewSpecSearch({
        specs: [],
        free_terms: trimmed.split(/\s+/),
        phrase: trimmed,
        understand: true,
      }),
    enabled: trimmed.length > 0,
    retry: false,
  });
}
