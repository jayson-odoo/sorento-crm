'use client';

import * as React from 'react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useClassificationEvidence } from '../../_shared/hooks/useFulfilmentPlanning';
import type {
  ClassificationEvidenceClass,
  ClassificationEvidenceLocation,
} from '../../_shared/types/fulfilmentPlanning.types';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

/**
 * The Proof button: the ranked evidence behind one item's hot/cold verdict.
 *
 * The captain, reading the trail: "don't give me jargon like abc classification, just tell
 * me hot selling or cold selling, at project or retail, with some button for me to view
 * detail as a proof ... like for this, you say dealer hot selling, what's the figure, and
 * what's the detail, I need proof". Every OTHER sentence on the board and the sheet already
 * says "hot" / "cold" / "not classified" in plain words; this is the one place the number
 * behind that word is shown, and it is read only when asked for (`enabled` on open).
 *
 * Same primitives as `BoardRankPopover`: a real `<table>` per class, not the shared DataGrid,
 * because this is a handful of rows of arithmetic inside a popover, not a listing.
 */
export function ClassificationProofPopover({
  productId,
  testId,
}: {
  productId?: string | null;
  /** Suffixed onto every `data-testid` this renders, so two Proof buttons on one screen
   * (the board's trail and the sheet's fact pill) never collide. */
  testId: string;
}) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading, isError } = useClassificationEvidence(productId, open);

  if (!productId) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Why hot or cold"
          data-testid={`classification-proof-${testId}`}
          className="inline-flex items-center rounded border border-border px-1.5 py-0.5 text-2xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(event) => event.stopPropagation()}
        >
          Proof
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="start"
          className="w-[420px] max-w-[92vw] p-0"
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          <div
            data-testid={`classification-proof-content-${testId}`}
            className="max-h-[60vh] overflow-y-auto"
          >
            <div className="border-b px-3 py-2 text-xs font-semibold">Hot or cold, and why</div>
            {isLoading && (
              <div className="space-y-2 p-3">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            )}
            {isError && !isLoading && (
              <p className="p-3 text-xs text-destructive">
                Could not load the evidence for this item.
              </p>
            )}
            {data && !isLoading && !isError && (
              <div className="divide-y">
                {data.classes.map((cls) => (
                  <ClassSection
                    key={cls.demand_class}
                    cls={cls}
                    hotCutPct={data.hot_cut_pct}
                    computedAt={data.computed_at}
                  />
                ))}
              </div>
            )}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function ClassSection({
  cls,
  hotCutPct,
  computedAt,
}: {
  cls: ClassificationEvidenceClass;
  hotCutPct: number;
  computedAt?: string | null;
}) {
  const heading = cls.demand_class === 'retail' ? 'Dealer (retail customers)' : 'Project';
  const verdictTone =
    cls.verdict === 'hot' ? 'pending' : cls.verdict === 'cold' ? 'draft' : 'unknown';
  const verdictLabel =
    cls.verdict === 'hot' ? 'Hot' : cls.verdict === 'cold' ? 'Cold' : 'Not classified';
  const computedText = computedAt ? ` · computed ${formatDateInMalaysia(computedAt)}` : '';

  return (
    <div className="px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-xs font-medium">{heading}</span>
        <span className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(verdictTone)}`}>
          {verdictLabel}
        </span>
      </div>
      {cls.locations.length === 0 ? (
        <p className="text-2xs text-muted-foreground">
          {`No ${cls.demand_class} deliveries of this item in the last 12 months.`}
        </p>
      ) : (
        <>
          <ScrollArea>
            <table className="w-auto min-w-full text-2xs tabular-nums">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="pe-2 text-start font-medium uppercase tracking-wide">Location</th>
                  <th className="pe-2 text-end font-medium uppercase tracking-wide">
                    Delivered last 12 months
                  </th>
                  <th className="pe-2 text-end font-medium uppercase tracking-wide">Rank</th>
                  <th className="pe-2 text-end font-medium uppercase tracking-wide">Its share</th>
                  <th className="text-end font-medium uppercase tracking-wide">Ranked above it</th>
                </tr>
              </thead>
              <tbody>
                {cls.locations.map((location) => (
                  <tr key={location.warehouse_code} className={location.hot ? 'font-medium' : ''}>
                    <td className="pe-2 py-0.5">{location.warehouse_code}</td>
                    <td className="pe-2 py-0.5 text-end">
                      {Number(location.qty_delivered).toLocaleString()}
                    </td>
                    <td className="pe-2 py-0.5 text-end">{`${location.rank} of ${location.of}`}</td>
                    <td className="pe-2 py-0.5 text-end">
                      {location.share_pct != null ? `${location.share_pct}%` : '-'}
                    </td>
                    <td className="py-0.5 text-end">{rankedAboveText(location, cls.demand_class)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
          <p className="mt-1.5 text-2xs text-muted-foreground">
            {`Hot = among the items that together make the first ${hotCutPct}% of quantity `}
            {`delivered to ${cls.demand_class} customers at that location${computedText}.`}
          </p>
        </>
      )}
    </div>
  );
}

/**
 * "93.6% of retail quantity" - the share held by every row ranked ahead of this one, so the
 * captain reads a thin ranking's row for what it is instead of mistaking its own cumulative
 * position ("Share: top 93.6%") for its own weight. `cumulative_share_pct` already includes
 * this row; subtracting `share_pct` leaves only what came before it.
 */
function rankedAboveText(
  location: ClassificationEvidenceLocation,
  demandClass: 'retail' | 'project',
): string {
  if (location.cumulative_share_pct == null || location.share_pct == null) return '-';
  // Independently-rounded inputs (cumulative to 1dp, its own share to 2dp) can leave a
  // hairline negative for the very top row; clamped, never a "-0%" the reader has to parse.
  const above = Math.max(
    0,
    Math.round((location.cumulative_share_pct - location.share_pct) * 10) / 10,
  );
  return `${above}% of ${demandClass} quantity`;
}

export default ClassificationProofPopover;
