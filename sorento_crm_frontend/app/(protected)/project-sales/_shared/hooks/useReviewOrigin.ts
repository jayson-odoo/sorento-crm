'use client';

import { useSearchParams } from 'next/navigation';
import { isSafeReviewOrigin } from '../lib/reviewOrigin';

/**
 * Reads the `from` origin a review page's own URL carries (S4, reviewOrigin.ts). `null` with
 * no origin - a deep link or a bookmark - which is what tells the caller to stay put on a
 * successful Confirm / Confirm schedule / Publish, exactly as before this slice. S1: a `from`
 * that is not a same-app relative path (a crafted external URL) is treated the same as absent,
 * never handed to `router.push`.
 */
export function useReviewOriginHref(): string | null {
  const searchParams = useSearchParams();
  const candidate = searchParams.get('from');
  return isSafeReviewOrigin(candidate) ? candidate : null;
}
