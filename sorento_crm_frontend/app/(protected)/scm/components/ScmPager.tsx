'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtInt } from '../lib/format';

/**
 * Client-side pager for the perspective card lists (warehouse tiles, supplier
 * cards). Mirrors the ProductListDialog footer pager (Prev / "Page X of Y" /
 * Next) so paging looks the same everywhere, and shows the in-scope total near
 * the control. Purely presentational - the caller owns the page state and slices
 * the already-fetched payload.
 */
export function ScmPager({
  page,
  pageCount,
  total,
  unit,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  /** In-scope total across all pages (shown as "82 warehouses"). */
  total: number;
  /** Singular noun for the total label, e.g. "warehouse" / "supplier". */
  unit: string;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-1">
      <span className="text-xs tabular-nums text-muted-foreground">
        {fmtInt(total)} {unit}
        {total === 1 ? '' : 's'}
      </span>
      {pageCount > 1 ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(Math.max(1, page - 1))}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="tabular-nums">
            Page {page} of {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pageCount}
            onClick={() => onPageChange(Math.min(pageCount, page + 1))}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
