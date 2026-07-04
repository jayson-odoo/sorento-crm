'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

export interface FindMatch {
  start: number;
  end: number;
}

export interface FindController {
  open: boolean;
  query: string;
  matches: FindMatch[];
  /** 0-based index of the active match, or -1 when there are none. */
  activeIndex: number;
  setQuery: (q: string) => void;
  openFind: () => void;
  close: () => void;
  next: () => void;
  prev: () => void;
}

/** Case-insensitive, non-overlapping substring matches. */
function computeMatches(text: string, query: string): FindMatch[] {
  if (!query) return [];
  const out: FindMatch[] = [];
  const haystack = text.toLowerCase();
  const needle = query.toLowerCase();
  let from = 0;
  // Cap to keep pathological queries (e.g. a single space over 100 KB) cheap.
  while (out.length < 5000) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1) break;
    out.push({ start: idx, end: idx + needle.length });
    from = idx + needle.length;
  }
  return out;
}

/**
 * Find-in-text state machine shared by the editable and read-only widgets.
 * Owns open/close, the query, the computed match ranges, and the active match
 * with wrap-around next/prev.
 */
export function useFindController(text: string): FindController {
  const [open, setOpen] = useState(false);
  const [query, setQueryState] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  const matches = useMemo(() => computeMatches(text, query), [text, query]);

  // Keep the active index in range as matches change (new query, edited text).
  useEffect(() => {
    if (matches.length === 0) {
      setActiveIndex(0);
      return;
    }
    setActiveIndex((i) => (i >= matches.length ? 0 : i < 0 ? 0 : i));
  }, [matches.length]);

  const setQuery = useCallback((q: string) => {
    setQueryState(q);
    setActiveIndex(0);
  }, []);

  const openFind = useCallback(() => setOpen(true), []);

  const close = useCallback(() => {
    setOpen(false);
    setQueryState('');
    setActiveIndex(0);
  }, []);

  const next = useCallback(() => {
    setActiveIndex((i) => (matches.length === 0 ? 0 : (i + 1) % matches.length));
  }, [matches.length]);

  const prev = useCallback(() => {
    setActiveIndex((i) =>
      matches.length === 0 ? 0 : (i - 1 + matches.length) % matches.length,
    );
  }, [matches.length]);

  return {
    open,
    query,
    matches,
    activeIndex: matches.length === 0 ? -1 : activeIndex,
    setQuery,
    openFind,
    close,
    next,
    prev,
  };
}
