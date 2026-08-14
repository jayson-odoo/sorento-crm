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
 * 1. matched   -> a link to the allocation, labelled with its SPO number.
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
    const label = allocation.spo_number?.trim() || stated || 'SPO allocation';
    return (
      <Link
        href={`/procurement-management/spo-allocations/${allocation.id}`}
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
