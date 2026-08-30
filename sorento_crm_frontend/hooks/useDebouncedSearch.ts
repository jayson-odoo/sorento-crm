'use client';

import { useCallback, useEffect, useState } from 'react';

/** What every list waited before asking the server (S7-02). */
export const SEARCH_DEBOUNCE_MS = 200;

export interface UseDebouncedSearchResult {
  /** What the box shows. Bind it to the input. */
  value: string;
  setValue: (next: string) => void;
  /** What the query asks for: trimmed, and one debounce behind the box. */
  debouncedValue: string;
  /** True while the box is ahead of the query, so the input can say so. */
  isSettling: boolean;
  /**
   * Set both halves at once, with no wait. For a search the reader did not type:
   * a remembered view being restored, or a picker being cleared as it reopens.
   * Debouncing those would flash the unfiltered list for 200ms first.
   */
  reset: (next?: string) => void;
}

/**
 * The one debounce behind every list's search box (S7-02).
 *
 * Twenty-two lists had written the same effect by hand, at 250ms or 300ms
 * depending on the week, and none of them told the reader that a request was
 * coming. So a search felt like a stall: the box had the word in it, the rows
 * still said the old thing, and nothing on screen accounted for the gap.
 *
 * 200ms is under the ~250ms at which a wait starts being read as the machine
 * ignoring you, and long enough that a typed word is one request rather than
 * five. `isSettling` is the other half: it is true exactly while the box and the
 * query disagree, which is the interval the reader is being asked to wait
 * through, and `ListSearchInput` renders it.
 *
 * Trims on the way out only. The box keeps the space the reader typed - deleting
 * it under the cursor is the kind of help nobody asked for - while the query
 * treats "ada " and "ada" as one search and does not re-ask.
 */
export function useDebouncedSearch(
  initialValue = '',
  delayMs: number = SEARCH_DEBOUNCE_MS,
): UseDebouncedSearchResult {
  const [value, setValue] = useState(initialValue);
  const [debouncedValue, setDebouncedValue] = useState(initialValue.trim());

  useEffect(() => {
    const trimmed = value.trim();
    // Nothing to settle: a trailing space must not schedule a re-render loop.
    if (trimmed === debouncedValue) return;
    const timer = window.setTimeout(() => setDebouncedValue(trimmed), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, debouncedValue, delayMs]);

  const reset = useCallback((next = '') => {
    setValue(next);
    setDebouncedValue(next.trim());
  }, []);

  return {
    value,
    setValue,
    debouncedValue,
    isSettling: value.trim() !== debouncedValue,
    reset,
  };
}
