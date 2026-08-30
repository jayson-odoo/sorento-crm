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
 *
 * It applies DURING the render, not in an effect. An effect runs after the first
 * commit, so the list would already have fired the query its defaults describe,
 * and the restored one a moment later: two requests on every Back, the first of
 * them for a page nobody asked for. Setting state during the render of the same
 * component is React's documented way to derive state from a changing input - it
 * re-renders before the children run, so only the restored query is ever issued.
 */

import { useMemo, useRef } from 'react';
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

  // The query string this list has already been restored to. A ref, not state:
  // it must be written in the same pass that applies, or the second render would
  // apply again and stamp on whatever the user has changed since.
  const appliedKey = useRef<string | null>(null);

  if (enabled && searchKey && appliedKey.current !== searchKey) {
    appliedKey.current = searchKey;
    apply(parseDetailSearch(new URLSearchParams(searchKey)));
  }
}
