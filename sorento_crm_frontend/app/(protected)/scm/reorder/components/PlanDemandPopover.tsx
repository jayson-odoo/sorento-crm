'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtInt } from '../../lib/format';
import { useRecommendationDemand } from '../hooks/useReorderRun';

/**
 * Which orders a planned quantity is actually for, behind an information icon on the row.
 *
 * > "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh"
 *
 * Both halves of that question are answered here rather than by opening the sales orders one
 * by one: the locations line says where the demand really sits, and the lines say which
 * orders, for how many, of what class, and when they are needed.
 *
 * Fetched on OPEN only. The row carries the total; pulling every contributing line for every
 * row on load is a cost nobody asked for.
 */
/**
 * The fetch lives in here, and this only mounts once the popover is OPEN.
 *
 * Keeping the query in the trigger meant every row on the grid held a react-query
 * subscription for a panel nobody had opened - hundreds of them on a full plan - and made
 * the drill unusable anywhere without a QueryClientProvider in scope.
 */
function PlanDemandBody({ runId, recId }: { runId: string | null; recId: string }) {
  const { data, isLoading, isError, error } = useRecommendationDemand(runId, recId, true);
  return (
    <>
      <div className="border-b px-3 py-2">
        <div className="text-xs font-semibold">Demand behind this row</div>
        {data ? (
          <p className="mt-0.5 text-2xs text-muted-foreground">
            {fmtInt(data.committed_total)} committed
            {data.unlocated_total > 0
              ? `, of which ${fmtInt(data.unlocated_total)} named no location`
              : ''}
            {data.locations.length ? ` · sits at ${data.locations.join(', ')}` : ''}
          </p>
        ) : null}
      </div>
      {isLoading ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : isError ? (
        <p className="p-3 text-2xs text-muted-foreground">
          {error instanceof Error ? error.message : 'Failed to load the demand.'}
        </p>
      ) : !data || !data.lines.length ? (
        <p className="p-3 text-2xs text-muted-foreground">
          No open order line sits behind this quantity. It was raised from forecast demand
          rather than from an order.
        </p>
      ) : (
        <>
          <ul className="max-h-72 divide-y overflow-y-auto">
            {data.lines.map((l, i) => (
              <li key={`${l.so_number}-${i}`} className="flex items-start gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium" title={l.so_number}>
                    {l.so_number}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-2xs text-muted-foreground">
                    {/* The location the ORDER named. "No location" is a fact about the
                        order, not a missing value, so it is said rather than dashed. */}
                    <Badge
                      variant={l.is_unlocated ? 'warning' : 'secondary'}
                      size="sm"
                      className="font-normal"
                    >
                      {l.warehouse_code ?? 'No location'}
                    </Badge>
                    {l.order_type ? <span className="capitalize">{l.order_type}</span> : null}
                    {l.required_date ? <span>needed {l.required_date}</span> : null}
                  </div>
                </div>
                <span className="shrink-0 text-xs font-medium tabular-nums">
                  {fmtInt(l.qty)}
                </span>
              </li>
            ))}
          </ul>
          {data.total > data.shown ? (
            <p className="border-t px-3 py-2 text-2xs text-muted-foreground">
              Showing {fmtInt(data.shown)} of {fmtInt(data.total)} lines.
            </p>
          ) : null}
        </>
      )}
    </>
  );
}

export function PlanDemandPopover({
  runId,
  recId,
  label = 'Demand behind this row',
}: {
  runId: string | null;
  recId: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          title={label}
          className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(e) => e.stopPropagation()}
        >
          <Info className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-[420px] p-0">
          {open ? <PlanDemandBody runId={runId} recId={recId} /> : null}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default PlanDemandPopover;
