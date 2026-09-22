'use client';

import * as React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { Table } from '@tanstack/react-table';
import { toast } from '@/lib/toast';

/**
 * Landing on an exact row from a link on ANOTHER page (S6, `PLAN-board-oi-mechanical-
 * 22sep.md`, AC-B6-3/4/5/10/11/12): a URL param names a row id, the grid (which pages
 * CLIENT-side, `getPaginationRowModel`) switches to the page holding it, scrolls it into
 * view and highlights it for ~2s, then strips the param so a refresh does not re-glow.
 *
 * Distinct from `components/ui/data-grid-table.tsx`'s own `from=` "Back to list" restore
 * (M5-07): that one fires when the READER presses Back from a detail page THIS table
 * itself linked to, on a whole-row `rowHref` the table renders every row with. This is a
 * link from an ENTIRELY DIFFERENT page (an OI row's own "SO line" cell, a SO line's own
 * "Order inquiry" cell) landing on a grid with no whole-row link at all - so it needs its
 * own id resolution, its own param name and its own clock, driven entirely by the caller.
 *
 * The caller wires the returned `rowId`/`rowClassName` into `<DataGrid rowAttributes=...
 * rowClassName=...>` (both already exist for exactly this kind of per-row styling, S4's
 * schedule-picker tint) - this hook touches no shared grid component.
 */
export function useTableDeepLinkHighlight<TData>(
  table: Table<TData>,
  options: {
    /** The URL param naming the target row's id (`line`, `row`, ...). */
    paramName: string;
    /** This row's own id, off `row.original`. */
    rowId: (row: TData) => string;
    /**
     * The grid's own search box text right now, and how to clear it (AC-B6-11): a
     * landing looks up the target ONLY once the search is empty, since a leftover search
     * from a previous visit could filter the very row this is looking for out of the row
     * model it is about to scan.
     */
    currentSearch: string;
    clearSearch?: () => void;
    /**
     * The rows are actually IN, ready to be searched (default `true`). The caller's own
     * `isLoading` (or similar) - the target row is not "not shown here" merely because the
     * fetch that would have carried it has not resolved yet; a landing that ran before the
     * data arrived would toast wrongly and strip the param before there was anything to
     * find it in.
     */
    enabled?: boolean;
  },
) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const target = searchParams.get(options.paramName);
  const [highlightId, setHighlightId] = React.useState<string | null>(null);
  const handled = React.useRef(false);
  const { clearSearch, currentSearch, rowId, enabled = true } = options;

  const stripParam = React.useCallback(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete(options.paramName);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, router, searchParams, options.paramName]);

  React.useEffect(() => {
    if (!target || handled.current || !enabled) return;
    // AC-B6-11: wait for the search box to empty - but only where the caller actually
    // gave us a way to empty it. Without `clearSearch` this returned every time and the
    // landing simply never happened: no glow, no toast, and the param left on the URL to
    // re-fire on the next render. A caller that cannot clear its search gets the lookup
    // against whatever is showing, which finds the row unless the search filtered it out,
    // and `not shown here` is the honest answer when it did.
    if (currentSearch && clearSearch) {
      clearSearch();
      return;
    }
    handled.current = true;
    const rows = table.getPrePaginationRowModel().rows;
    const index = rows.findIndex((row) => rowId(row.original) === target);
    if (index === -1) {
      // AC-B6-5/AC-B6-12: not found (wrong id, a hidden cancelled row, or simply not on
      // this loaded set) - nothing glows, and this is information, not a failure.
      toast.info('That line is not shown here');
      stripParam();
      return;
    }
    const pageSize = table.getState().pagination.pageSize;
    table.setPageIndex(Math.floor(index / pageSize));
    setHighlightId(target);
    stripParam();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, currentSearch, enabled]);

  React.useEffect(() => {
    if (!highlightId) return;
    const timer = setTimeout(() => setHighlightId(null), 2000);
    return () => clearTimeout(timer);
  }, [highlightId]);

  React.useEffect(() => {
    if (!highlightId) return;
    // jsdom implements no scrollIntoView, hence the optional call.
    const reducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document
      .getElementById(deepLinkRowDomId(highlightId))
      ?.scrollIntoView?.({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' });
  }, [highlightId]);

  return {
    highlightId,
    /** Spread into `<DataGrid rowAttributes={...}>` so the highlighted row can be found
     * by `scrollIntoView` without the caller wiring its own ref per row. */
    rowAttributes: (row: TData) => ({ id: deepLinkRowDomId(rowId(row)) }),
    /** Spread into `<DataGrid rowClassName={...}>`; the class itself lives beside
     * `.jump-flash` in `css/styles.css` (AC-B6-6: an existing colour token, its own 2s
     * fade, and an instant on/off under reduced motion). */
    rowClassName: (row: TData) =>
      highlightId && rowId(row) === highlightId ? 'deep-link-highlight' : undefined,
  };
}

function deepLinkRowDomId(id: string): string {
  return `deep-link-row-${id}`;
}
