'use client';

/**
 * The chip search every document list shares (SEARCH-CHIPS), lifted out of the Sales orders
 * grid so each list holds the same rules rather than its own copy.
 *
 * Each chip and the typed text is one value; a row matching any of them is listed (the
 * backend's rule, `app/utils/list_search.py`).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from 'react';
import { addSearchChips } from '@/lib/searchChips';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';

export interface UseListChipSearchResult {
  /** What the box shows. */
  searchInput: string;
  /** Emptied text (a chip committed, Clear) settles at once: a debounced stale word would
   * send one more request with it. */
  setSearchInput: (next: string) => void;
  chips: string[];
  setChips: (next: string[]) => void;
  /** The chips plus the debounced typed text: what the list GET sends as `query`. */
  searchTerms: string[];
  /** One string per distinct `searchTerms`, for effect and reset dependencies. */
  searchTermsKey: string;
  /** True while the box is ahead of the query. */
  isSettling: boolean;
  /** A URL's `query` values back as chips, the typed text emptied, at once. */
  restore: (values: string[] | undefined) => void;
  /** The address-bar search the list last wrote itself; hand it to `useSearchInAddressBar`. */
  writtenSearch: MutableRefObject<string | null>;
  /** True while the address bar still holds the list's own write: reading it back from
   * `useListStateFromUrl` would turn the typed text into a chip. */
  isOwnWrite: () => boolean;
}

function isOwnWriteOf(written: MutableRefObject<string | null>): boolean {
  return (
    written.current !== null &&
    window.location.search.slice(1) === written.current
  );
}

/** `initialChips`: a list that reads its URL once, at mount, starts with those values. */
export function useListChipSearch(initialChips?: string[]): UseListChipSearchResult {
  const {
    value: searchInput,
    setValue,
    debouncedValue,
    isSettling,
    reset,
  } = useDebouncedSearch();
  const [chips, setChips] = useState<string[]>(() =>
    initialChips ? addSearchChips([], initialChips).chips : [],
  );
  const writtenSearch = useRef<string | null>(null);

  const searchTerms = useMemo(
    () => addSearchChips(chips, [debouncedValue]).chips,
    [chips, debouncedValue],
  );
  const searchTermsKey = searchTerms.join('\n');

  const setSearchInput = useCallback(
    (next: string) => (next === '' ? reset('') : setValue(next)),
    [reset, setValue],
  );

  const restore = useCallback(
    (values: string[] | undefined) => {
      setChips(addSearchChips([], values ?? []).chips);
      reset('');
    },
    [reset],
  );

  const isOwnWrite = useCallback(() => isOwnWriteOf(writtenSearch), []);

  return {
    searchInput,
    setSearchInput,
    chips,
    setChips,
    searchTerms,
    searchTermsKey,
    isSettling,
    restore,
    writtenSearch,
    isOwnWrite,
  };
}

export interface UseSearchInAddressBarOptions {
  /** The list's whole state as a query string (no leading `?`). */
  detailSearch: string;
  searchTermsKey: string;
  /** False where the URL is not the list's own (a list embedded in a record). */
  enabled: boolean;
  /** `useListChipSearch().writtenSearch`, so the list's URL restore can skip its own write. */
  writtenSearch?: MutableRefObject<string | null>;
}

/**
 * Once the search has changed, the list keeps its whole state in the address bar (Q5b), so a
 * refresh keeps the chips. Never on the first render, never while `enabled` is false.
 *
 * Records each write in `writtenSearch` (the list's `isOwnWrite()` reads it).
 */
export function useSearchInAddressBar({
  detailSearch,
  searchTermsKey,
  enabled,
  writtenSearch,
}: UseSearchInAddressBarOptions): void {
  const ownWritten = useRef<string | null>(null);
  const written = writtenSearch ?? ownWritten;
  const searchTermsSeen = useRef<string | null>(null);
  const searchTouched = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    if (searchTermsSeen.current === null) {
      searchTermsSeen.current = searchTermsKey;
      return;
    }
    if (searchTermsSeen.current !== searchTermsKey) {
      searchTermsSeen.current = searchTermsKey;
      searchTouched.current = true;
    }
    if (!searchTouched.current || window.location.search.slice(1) === detailSearch) return;
    written.current = detailSearch;
    window.history.replaceState(
      window.history.state,
      '',
      detailSearch ? `?${detailSearch}` : window.location.pathname,
    );
  }, [detailSearch, searchTermsKey, enabled, written]);
}
