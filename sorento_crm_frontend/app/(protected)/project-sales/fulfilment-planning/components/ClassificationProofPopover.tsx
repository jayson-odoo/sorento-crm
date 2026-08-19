'use client';

import * as React from 'react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useClassificationEvidence } from '../../_shared/hooks/useFulfilmentPlanning';
import type { ClassificationEvidenceClass } from '../../_shared/types/fulfilmentPlanning.types';

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
          <table className="w-full text-2xs tabular-nums">
            <thead>
              <tr className="text-muted-foreground">
                <th className="pe-2 text-start font-medium uppercase tracking-wide">Location</th>
                <th className="pe-2 text-end font-medium uppercase tracking-wide">
                  Delivered last 12 months
                </th>
                <th className="pe-2 text-end font-medium uppercase tracking-wide">Rank</th>
                <th className="text-end font-medium uppercase tracking-wide">Share</th>
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
                  <td className="py-0.5 text-end">
                    {location.cumulative_share_pct != null
                      ? `top ${location.cumulative_share_pct}%`
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1.5 text-2xs text-muted-foreground">
            {`Hot = inside the top ${hotCutPct}% of quantity delivered to ${cls.demand_class} `}
            {`customers, over every item at every location${computedText}.`}
          </p>
        </>
      )}
    </div>
  );
}

export default ClassificationProofPopover;
