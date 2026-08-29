'use client';

/**
 * Restore a list's state from the URL it was returned to.
 *
 * The detail page's Back hands the list its own query string back (S3-01), and
 * the pager's steps keep rewriting it. That is only worth anything if the list
 * READS it: before S3 three lists did, in three hand-rolled effects, and
 * fourteen ignored it entirely, so Back landed the user on page 1 of an
 * unfiltered list and the pager's cache entry was never the one the list refilled.
 *
 * One hook, one parse (`parseDetailSearch`, the same one `useListPager` uses), and
 * the caller says what to do with the values. It fires once per distinct query
 * string, and never on an empty one: a list opened fresh from the sidebar keeps
 * its own defaults rather than being reset to the parser's.
 */

import { useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import type { ListPagerParams } from '@/hooks/useListPager';

export interface UseListStateFromUrlOptions {
  /**
   * Off while the list must ignore the URL - the products list treats a hard
   * refresh as a clean slate, so it passes `enabled: !isReload`.
   */
  enabled?: boolean;
}

export function useListStateFromUrl(
  apply: (state: ListPagerParams) => void,
  { enabled = true }: UseListStateFromUrlOptions = {},
): void {
  const searchParams = useSearchParams();
  const searchKey = useMemo(() => searchParams.toString(), [searchParams]);

  // The callback closes over the list's setters, so it changes on every render.
  // Keeping it in a ref is what lets the effect depend on the URL alone.
  const applyRef = useRef(apply);
  applyRef.current = apply;

  useEffect(() => {
    if (!enabled || !searchKey) return;
    applyRef.current(parseDetailSearch(new URLSearchParams(searchKey)));
  }, [searchKey, enabled]);
}
