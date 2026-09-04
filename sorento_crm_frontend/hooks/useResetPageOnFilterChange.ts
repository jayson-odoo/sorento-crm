'use client';

/**
 * Send the reader back to page one when a filter CHANGES, and never on mount.
 *
 * Every list needs this: staying on page 7 of a set that just got smaller shows
 * an empty table. Almost every list wrote it as a bare
 * `useEffect(() => setPagination(p => ({ ...p, pageIndex: 0 })), [filters])` -
 * and a `useEffect` always runs once after the first commit, filter change or
 * not. That mount run is what silently undid the whole Back-to-list round trip:
 * `useListStateFromUrl` restores `page=2` DURING the render, the list commits on
 * page 2, and then this effect fires and stamps page 1 over it. The URL was
 * right, the fetch for page 2 even went out, and the grid still showed page 1
 * (M5 run 2 evidence, finding 3 - Products, `?page=2` in the address bar,
 * "1 - 50 of 11672" in the footer, zero `[data-returned="true"]` rows).
 *
 * Two lists had already hand-rolled a `filtersMounted` ref against this. A ref
 * that only says "have I run before" is not enough either: React's StrictMode
 * runs effects twice on mount, and the second run reads as a change. So this
 * compares the dependency VALUES, and resets only when one of them actually
 * moved.
 *
 * Pass the same values you would have put in the effect's dependency array. They
 * must be stable between renders when nothing changed - join an array into a
 * string rather than passing the array, exactly as the hand-rolled versions did,
 * or a fresh identity every render reads as a filter change every render.
 */

import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import type { PaginationState } from '@tanstack/react-table';

export function useResetPageOnFilterChange(
  setPagination: Dispatch<SetStateAction<PaginationState>>,
  deps: readonly unknown[],
): void {
  // No dependency array on the effect itself: the comparison below is the
  // dependency check, and it is the one that can tell "mounted" and "changed"
  // apart. Comparing values also survives StrictMode's double invoke, which a
  // "have I run yet" ref does not.
  const previous = useRef<readonly unknown[] | null>(null);

  useEffect(() => {
    const before = previous.current;
    previous.current = deps;

    // First commit. Whatever page the list is on is the page it was ASKED for -
    // its own default, or the one `useListStateFromUrl` restored from the URL.
    if (before === null) return;

    const unchanged =
      before.length === deps.length &&
      before.every((value, index) => Object.is(value, deps[index]));
    if (unchanged) return;

    setPagination((current) =>
      current.pageIndex === 0 ? current : { ...current, pageIndex: 0 },
    );
  });
}
