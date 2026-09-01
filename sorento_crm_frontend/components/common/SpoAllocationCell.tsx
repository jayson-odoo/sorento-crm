'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export type SpoAllocationCellProps = {
  /** The allocation the line was matched to, when the matcher found one. */
  allocation?: { id: string; spo_number?: string | null } | null;
  /** `spo_number_raw` - the SPO the imported sheet stated for this line. */
  statedSpoNumber?: string | null;
  className?: string;
};

/**
 * The SPO Allocation cell of a picking line, shared by the GRN detail line
 * table and the Picking Lines listing so the three states below cannot drift
 * apart between them.
 *
 * 1. matched   -> a link to the SPO DOCUMENT (the allocation's `spo_number`,
 *                 slash-encoded, same as `PackingListLinesTab.tsx`) - never the
 *                 allocation's own uuid, which the standalone per-allocation
 *                 detail route (retired, PLAN-spo-investigation-grid.md) used to
 *                 take. A matched allocation with no `spo_number` of its own
 *                 (data gap) renders the same label with no link - there is no
 *                 document for it to open.
 * 2. stated    -> the SPO number the sheet claimed, muted, plus an "Unmatched"
 *                 badge. A dash here would read as "the sheet said nothing",
 *                 which is false and sends the user hunting.
 * 3. neither   -> a dash.
 */
export function SpoAllocationCell({
  allocation,
  statedSpoNumber,
  className,
}: SpoAllocationCellProps) {
  const stated = statedSpoNumber?.trim() || '';

  if (allocation) {
    const spoNumber = allocation.spo_number?.trim() || '';
    const label = spoNumber || stated || 'SPO allocation';
    if (!spoNumber) {
      return (
        <span className={cn('font-medium truncate', className)} title={label}>
          {label}
        </span>
      );
    }
    return (
      <Link
        href={`/procurement-management/spo-allocations/${encodeURIComponent(spoNumber)}`}
        className={cn('text-primary hover:underline font-medium truncate', className)}
        title={label}
      >
        {label}
      </Link>
    );
  }

  if (stated) {
    return (
      <span className={cn('flex w-full min-w-0 items-center gap-1.5', className)}>
        <span className="text-muted-foreground truncate" title={stated}>
          {stated}
        </span>
        <Badge variant="warning" appearance="light" size="sm" className="shrink-0">
          Unmatched
        </Badge>
      </span>
    );
  }

  return <span className={cn('text-muted-foreground', className)}>-</span>;
}
