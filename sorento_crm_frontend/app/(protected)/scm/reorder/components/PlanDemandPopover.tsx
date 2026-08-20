'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { fmtInt, fmtSupplierCost } from '../../lib/format';
import { DemandContextHeader } from './DemandContextHeader';
import { orderInquiryWorklistHref } from '../lib/orderInquiryLink';
import { PLAN_CHANNEL_LABEL, type PlanChannel } from '../lib/planLineGrouping';
import { useRecommendationDemand } from '../hooks/useReorderRun';
import type { PlanDemand } from '../services/reorderRunService';

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
/**
 * The one line the header says: how much is committed, and WHERE this list is drawn from.
 *
 * The scope is the whole point (AC-1.1/AC-1.2). With pool netting off the list is the
 * row's own warehouse and the total is the row's own SO figure; with it on the plan netted
 * the pool together, so the pool is named rather than left for the reader to infer from a
 * list of locations they did not order for.
 */
export function describeDemandScope(data: PlanDemand): string {
  const at = data.locations.length ? ` at ${data.locations.join(', ')}` : '';
  const pool = data.scope === 'pool' && data.pool_code ? ` (pool ${data.pool_code})` : '';
  const unlocated =
    data.unlocated_total > 0 ? `, incl. ${fmtInt(data.unlocated_total)} unlocated` : '';
  return `${fmtInt(data.committed_total)} committed${at}${pool}${unlocated}`;
}

/**
 * A quiet second line under the scope sentence: how the committed total splits by
 * channel (captain follow-up, 20 Aug). `null` when the response carries none of the
 * three totals - a cached/legacy payload predating the field - so the caller renders
 * nothing rather than a line of zeros nobody stated.
 */
export function describeDemandTotals(data: PlanDemand): string | null {
  if (
    data.project_total === undefined &&
    data.retail_total === undefined &&
    data.unclassified_total === undefined
  ) {
    return null;
  }
  const parts = [
    `Project ${fmtInt(data.project_total ?? 0)}`,
    `Retail ${fmtInt(data.retail_total ?? 0)}`,
  ];
  if (data.unclassified_total) parts.push(`Unclassified ${fmtInt(data.unclassified_total)}`);
  return parts.join(' - ');
}

/**
 * What each `PlanDemandLine.source` chip says, and the fuller sentence its title spells
 * out (captain: "for project is order inquiry, for retail is sales order directly").
 *
 * `order_inquiry` used to read "OI" and link to the worklist unconditionally - but the
 * flag it is built from (`demand_origin`) is a permanent stamp on the ORDER, made the
 * moment the Order Inquiry import creates it, and it survives long after CS has worked
 * through every row off that order. Measured: 605 core sales orders carry the stamp; only
 * 7 still have a live Order Inquiry row. "OI" promised a worklist entry that, almost every
 * time, was not there. "OI import" says what actually happened - this order was CREATED
 * BY the import - without claiming a live row exists; the click-through below is now
 * gated on `has_inquiry_row`, the fact that answers that.
 */
const SOURCE_CHIP: Record<string, { chip: string; title: string }> = {
  sales_order: { chip: 'SO', title: 'Direct sales order' },
  order_inquiry: {
    chip: 'OI import',
    title: 'Order created by the Order Inquiry import',
  },
  order_inquiry_confirmed: { chip: 'OI confirmed', title: 'Confirmed for buy by CS' },
};

/**
 * Project vs Retail (captain, 20 Aug: "let me see the retail SO also"). The backend has
 * always sent `demand_class` on every line - `sales_order`-sourced lines ARE the retail
 * (and unclassified) ones, since a project-class order only reaches this list via the
 * `order_inquiry` source - but this popover never rendered it, so a retail line and a
 * project line looked identical beside the "SO" provenance chip. Colours match the plan
 * grid's own Project/Retail chip (`PlanLinesGrid`) so the same word means the same colour
 * across the screen.
 */
function ClassChip({ demandClass }: { demandClass: string | null | undefined }) {
  if (demandClass === 'project') {
    return (
      <Badge variant="info" appearance="light" size="sm" className="font-normal">
        Project
      </Badge>
    );
  }
  if (demandClass) {
    return (
      <Badge variant="success" appearance="light" size="sm" className="font-normal">
        Retail
      </Badge>
    );
  }
  return (
    <Badge variant="warning" appearance="light" size="sm" className="font-normal">
      Unclassified
    </Badge>
  );
}

function PlanDemandBody({
  runId,
  recId,
  channel,
}: {
  runId: string | null;
  recId: string;
  /** Narrows the fetch AND the header to one channel (captain's own preferred fix, 20
   *  Aug) - so a trigger sitting on the Project cell can never open a list that turns
   *  out to be mostly Retail. `undefined` keeps the old unfiltered "whole row" popover. */
  channel?: PlanChannel;
}) {
  const { data, isLoading, isError, error } = useRecommendationDemand(
    runId,
    recId,
    true,
    channel,
  );
  // N-6 (reviewer): computed once - `describeDemandTotals` was called twice for the same
  // `data`, once to decide whether to render the line and again to render it. Skipped
  // entirely when `channel` is set: a per-channel breakdown line under an already
  // channel-scoped header is redundant at best, and reads as "0 of the other two" at
  // worst - the header's own total is the one figure this popover is now making.
  const demandTotals = !channel && data ? describeDemandTotals(data) : null;
  const heading = channel ? `${PLAN_CHANNEL_LABEL[channel]} demand behind this row` : 'Demand behind this row';
  return (
    <>
      <div className="border-b px-3 py-2">
        <div className="text-xs font-semibold">{heading}</div>
        {data ? (
          <p className="mt-0.5 text-2xs text-muted-foreground">{describeDemandScope(data)}</p>
        ) : null}
        {demandTotals ? (
          <p className="mt-0.5 text-2xs text-muted-foreground">{demandTotals}</p>
        ) : null}
        {data ? <DemandContextHeader data={data} /> : null}
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
          {channel
            ? `No open ${PLAN_CHANNEL_LABEL[channel].toLowerCase()} order line sits behind this quantity.`
            : 'No open order line sits behind this quantity. It was raised from forecast demand rather than from an order.'}
        </p>
      ) : (
        <>
          <ul className="max-h-72 divide-y overflow-y-auto">
            {data.lines.map((l, i) => (
              <li key={`${l.so_number}-${i}`} className="flex items-start gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  {/* Click-through to the Order Inquiry worklist, scoped to this SO
                      (captain, 20 Aug) - but only when a row is actually there to find.
                      `order_inquiry_confirmed` is BUILT from a live row, so it always
                      links. A bare `order_inquiry` is only a stamp on the order (it was
                      CREATED by the import) and most of the time CS has already worked
                      through every row off it - linking on the stamp alone sent the
                      captain to a worklist filtered to nothing. `has_inquiry_row` is the
                      fact that actually answers "is there something to open". */}
                  {l.source === 'order_inquiry_confirmed' ||
                  (l.source === 'order_inquiry' && l.has_inquiry_row) ? (
                    <Link
                      href={orderInquiryWorklistHref(l.so_number)}
                      onClick={(e) => e.stopPropagation()}
                      className="truncate text-xs font-medium hover:text-primary hover:underline"
                      title={`Open ${l.so_number} on the Order Inquiry worklist`}
                    >
                      {l.so_number}
                    </Link>
                  ) : (
                    <div className="truncate text-xs font-medium" title={l.so_number}>
                      {l.so_number}
                    </div>
                  )}
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
                    <ClassChip demandClass={l.demand_class} />
                    {l.source && SOURCE_CHIP[l.source] ? (
                      <Badge
                        variant="secondary"
                        appearance="light"
                        size="sm"
                        className="font-normal text-muted-foreground"
                        title={SOURCE_CHIP[l.source].title}
                      >
                        {SOURCE_CHIP[l.source].chip}
                      </Badge>
                    ) : null}
                    {l.order_type ? <span className="capitalize">{l.order_type}</span> : null}
                    {l.required_date ? <span>needed {l.required_date}</span> : null}
                  </div>
                  {/* Who ordered it and what they pay. The "it sells RM 0.94" question is
                      answerable from the order itself rather than from a second screen;
                      a line the extract carries no price for simply says nothing. */}
                  <div className="mt-0.5 flex items-baseline gap-1.5 text-2xs text-muted-foreground">
                    <span className="min-w-0 flex-1 truncate" title={l.customer_label}>
                      {l.customer_label}
                    </span>
                    {l.unit_price !== null && l.unit_price !== undefined ? (
                      <span className="shrink-0 tabular-nums">
                        {fmtSupplierCost(l.unit_price, null)}
                      </span>
                    ) : null}
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
  label,
  channel,
}: {
  runId: string | null;
  recId: string;
  /** Defaults to the channel-aware label when `channel` is set, so a trigger mounted on
   *  the Retail cell announces itself as "Retail demand..." rather than the generic
   *  wording of the row-level trigger. */
  label?: string;
  /** Narrows this ONE trigger's drill to a single channel (captain's own preferred fix,
   *  20 Aug: "put the icon at project and retail separately") - `undefined` is the
   *  original row-level, unfiltered popover, still used where a cell is not itself
   *  channel-specific. */
  channel?: PlanChannel;
}) {
  const [open, setOpen] = useState(false);
  const resolvedLabel =
    label ?? (channel ? `${PLAN_CHANNEL_LABEL[channel]} demand behind this row` : 'Demand behind this row');

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={resolvedLabel}
          title={resolvedLabel}
          className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(e) => e.stopPropagation()}
        >
          <Info className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-[26rem] max-w-[92vw] p-0">
          {open ? <PlanDemandBody runId={runId} recId={recId} channel={channel} /> : null}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default PlanDemandPopover;
