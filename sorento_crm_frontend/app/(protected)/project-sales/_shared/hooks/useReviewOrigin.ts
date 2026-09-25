'use client';

import { useSearchParams } from 'next/navigation';

/**
 * Reads the `from` origin a review page's own URL carries (S4, reviewOrigin.ts). `null` with
 * no origin - a deep link or a bookmark - which is what tells the caller to stay put on a
 * successful Confirm / Confirm schedule / Publish, exactly as before this slice.
 */
export function useReviewOriginHref(): string | null {
  const searchParams = useSearchParams();
  return searchParams.get('from') || null;
}
