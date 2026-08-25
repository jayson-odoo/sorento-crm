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
import type { PlanDemand, PlanDemandHistoryLine, PlanDemandLine } from '../services/reorderRunService';

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
 *
 * TWO SURFACES, TWO QUESTIONS (captain, live test, 21 Aug): "on the location rows you show
 * me the demand, not the history; on the product row you show me the history, not the
 * demand." A group panel member row (per LOCATION) still opens the open-committed-demand
 * list this popover always showed - `scope` is unset there. The top PRODUCT-grain row's own
 * trigger (`scope="product"`) instead opens ONLY the trailing-window order-history section -
 * "what's the sales order for the past year/3 months" - because that row's own number is
 * already the union across every one of the product's locations, and stacking BOTH the open
 * list and the history under it answered two different questions in one popover, which read
 * as one bloated answer to neither. `scope` is therefore what decides which body renders,
 * not a separate flag - the two are the same trigger by construction (see `PlanLinesGrid`).
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

/**
 * The SO number, as a link to the sales order's own record (21 Aug follow-up: "SO numbers
 * in both views become hyperlinks to the sales order's own record") - `/scm/sales-orders/
 * {so_id}`, the SAME target `SalesOrdersList` itself links a row to (`so.id`, the CORE
 * `sales_orders` row, never the recommendation/product id). Every demand and history line
 * traces back to a core SO by construction (even the confirmed leg, via
 * `core_sales_order_line_id`), so this is never a dead link where `so_id` is present.
 * Falls back to plain text on a cached response predating the field.
 */
function SoNumberLink({ soId, soNumber }: { soId?: string | null; soNumber: string }) {
  if (!soId) {
    return (
      <span className="truncate text-xs font-medium" title={soNumber}>
        {soNumber}
      </span>
    );
  }
  return (
    <Link
      href={`/scm/sales-orders/${encodeURIComponent(soId)}`}
      onClick={(e) => e.stopPropagation()}
      className="truncate text-xs font-medium hover:text-primary hover:underline"
      title={`Open ${soNumber}`}
    >
      {soNumber}
    </Link>
  );
}

/**
 * The Order-Inquiry-worklist click-through (captain, 20 Aug), now a small SEPARATE link
 * beside the chips rather than riding on the SO number itself - the SO number's own link
 * is `SoNumberLink` above, uniform across every line. Renders only when a row is actually
 * there to find (`has_inquiry_row` / the confirmed leg, which is always built from one).
 */
function OrderInquiryWorklistLink({ line }: { line: PlanDemandLine }) {
  const eligible =
    line.source === 'order_inquiry_confirmed' ||
    (line.source === 'order_inquiry' && line.has_inquiry_row);
  if (!eligible) return null;
  return (
    <Link
      href={orderInquiryWorklistHref(line.so_number)}
      onClick={(e) => e.stopPropagation()}
      className="text-2xs text-muted-foreground hover:text-primary hover:underline"
      title={`Open ${line.so_number} on the Order Inquiry worklist`}
    >
      OI worklist
    </Link>
  );
}

function DemandBody({ data, channel }: { data: PlanDemand; channel?: PlanChannel }) {
  // N-6 (reviewer): computed once - `describeDemandTotals` was called twice for the same
  // `data`, once to decide whether to render the line and again to render it. Skipped
  // entirely when `channel` is set: a per-channel breakdown line under an already
  // channel-scoped header is redundant at best, and reads as "0 of the other two" at
  // worst - the header's own total is the one figure this popover is now making.
  const demandTotals = !channel ? describeDemandTotals(data) : null;
  return (
    <>
      <div className="border-b px-3 py-2">
        <div className="text-xs font-semibold">
          {channel ? `${PLAN_CHANNEL_LABEL[channel]} demand behind this row` : 'Demand behind this row'}
        </div>
        <p className="mt-0.5 text-2xs text-muted-foreground">{describeDemandScope(data)}</p>
        {demandTotals ? (
          <p className="mt-0.5 text-2xs text-muted-foreground">{demandTotals}</p>
        ) : null}
      </div>
      {!data.lines.length ? (
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
                  <div className="flex items-center gap-1.5">
                    <SoNumberLink soId={l.so_id} soNumber={l.so_number} />
                    <OrderInquiryWorklistLink line={l} />
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
                  {/* Who ordered it, who sold it, and what they pay. The "it sells RM
                      0.94" question is answerable from the order itself rather than from
                      a second screen; a line the extract carries no price for simply
                      says nothing, and the same for an order with no agent on file. */}
                  <div className="mt-0.5 flex items-baseline gap-1.5 text-2xs text-muted-foreground">
                    <span className="min-w-0 flex-1 truncate" title={l.customer_label}>
                      {l.customer_label}
                      {l.agent_label ? ` · ${l.agent_label}` : ''}
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

/**
 * "For project, what's the sales order for the past year, who is the customer and agent...
 * for retail, past 3 months, same" (captain, 21 Aug) - the TOP product-grain row's own
 * drill (`scope="product"`), fed by `history_lines`: every order PLACED in the trailing
 * window (`project_window_months`/`retail_window_months`, the SAME window
 * `project_12m_qty`/`retail_3m_qty` already total), delivered or not, marked via
 * `delivered`. This is the WHOLE body for that trigger - never stacked with the
 * open-demand list, which is the other surface's own answer (see the file header).
 */
function HistoryBody({ data, channel }: { data: PlanDemand; channel: PlanChannel }) {
  const lines = data.history_lines ?? [];
  const months =
    channel === 'project' ? data.project_window_months : data.retail_window_months;
  return (
    <>
      <div className="border-b px-3 py-2">
        <div className="text-xs font-semibold">{`${PLAN_CHANNEL_LABEL[channel]} order history`}</div>
        <DemandContextHeader data={data} channel={channel} />
      </div>
      {!lines.length ? (
        <p className="p-3 text-2xs text-muted-foreground">
          {`No ${PLAN_CHANNEL_LABEL[channel].toLowerCase()} orders in the last ${months ?? '-'} full months.`}
        </p>
      ) : (
        <>
          <ul className="max-h-72 divide-y overflow-y-auto">
            {lines.map((l: PlanDemandHistoryLine, i: number) => (
              <li key={`${l.so_number}-hist-${i}`} className="flex items-start gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <SoNumberLink soId={l.so_id} soNumber={l.so_number} />
                    <Badge
                      variant={l.delivered ? 'success' : 'secondary'}
                      appearance="light"
                      size="sm"
                      className="font-normal"
                    >
                      {l.delivered ? 'Delivered' : 'Open'}
                    </Badge>
                    {l.order_date ? (
                      <span className="text-2xs text-muted-foreground">{l.order_date}</span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex items-baseline gap-1.5 text-2xs text-muted-foreground">
                    <span className="min-w-0 flex-1 truncate" title={l.customer_label}>
                      {l.customer_label}
                      {l.agent_label ? ` · ${l.agent_label}` : ''}
                    </span>
                    {l.unit_price !== null && l.unit_price !== undefined ? (
                      <span className="shrink-0 tabular-nums">
                        {fmtSupplierCost(l.unit_price, null)}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span className="shrink-0 text-xs font-medium tabular-nums">{fmtInt(l.qty)}</span>
              </li>
            ))}
          </ul>
          {(data.history_total ?? lines.length) > lines.length ? (
            <p className="border-t px-3 py-2 text-2xs text-muted-foreground">
              Showing {fmtInt(lines.length)} of {fmtInt(data.history_total ?? lines.length)} orders.
            </p>
          ) : null}
        </>
      )}
    </>
  );
}

function PlanDemandBody({
  runId,
  recId,
  channel,
  scope,
}: {
  runId: string | null;
  recId: string;
  /** Narrows the fetch AND the header to one channel (captain's own preferred fix, 20
   *  Aug) - so a trigger sitting on the Project cell can never open a list that turns
   *  out to be mostly Retail. `undefined` keeps the old unfiltered "whole row" popover. */
  channel?: PlanChannel;
  /** The top product-grain row's own trigger (21 Aug follow-up) - widens the fetch to
   *  every recommendation the run wrote for the same product, AND switches the body from
   *  the open-demand list to the order-history section (see the file header: "two
   *  surfaces, two questions"). `undefined` keeps the demand-list body every other
   *  caller already gets. */
  scope?: 'product';
}) {
  const { data, isLoading, isError, error } = useRecommendationDemand(
    runId,
    recId,
    true,
    channel,
    scope,
  );
  const isHistory = scope === 'product';
  return (
    <>
      {isLoading ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : isError ? (
        <p className="p-3 text-2xs text-muted-foreground">
          {error instanceof Error
            ? error.message
            : `Failed to load the ${isHistory ? 'order history' : 'demand'}.`}
        </p>
      ) : !data ? null : isHistory && channel ? (
        // The history body reports ONE channel's window (P5), so it needs to be told which.
        // Every `scope="product"` trigger names one; a caller that did not has no window to
        // report and falls through to the demand list, which was always the other answer.
        <HistoryBody data={data} channel={channel} />
      ) : (
        <DemandBody data={data} channel={channel} />
      )}
    </>
  );
}

export function PlanDemandPopover({
  runId,
  recId,
  label,
  channel,
  scope,
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
  /** Widens this ONE trigger's drill to every recommendation the run wrote for the same
   *  product, AND switches it to the order-HISTORY body (21 Aug follow-up: "put the
   *  tooltip on the TOP product-grain row too" - then, live-tested, "you show me the
   *  history, not the demand" for that row specifically). `undefined` is the existing
   *  single-row, open-demand scope, used by the ungrouped grid's rows and the group
   *  panel's per-location rows. */
  scope?: 'product';
}) {
  const [open, setOpen] = useState(false);
  const isHistory = scope === 'product';
  const resolvedLabel =
    label ??
    (channel
      ? `${PLAN_CHANNEL_LABEL[channel]} ${isHistory ? 'order history' : 'demand behind this row'}`
      : 'Demand behind this row');

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
          {open ? (
            <PlanDemandBody runId={runId} recId={recId} channel={channel} scope={scope} />
          ) : null}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default PlanDemandPopover;
