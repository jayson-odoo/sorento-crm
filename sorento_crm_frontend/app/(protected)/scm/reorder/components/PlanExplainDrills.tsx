'use client';

import Link from 'next/link';
import { Info } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtDecimal, fmtInt, fmtSigned, fmtSupplierCost } from '../../lib/format';
import { useExplainDemand, useExplainNet } from '../hooks/useDrills';
import { m8CashImpact, type M8PlanRow } from '../lib/planRow';

/**
 * The explain drills - why this quantity, why this net, why this runway.
 *
 * Lifted out of the old hand-rolled results grid unchanged so the new DataGrid can carry them.
 * They are the reason the plan is trustworthy: a buy quantity nobody can interrogate is a
 * number the buyer has to take on faith, and every one of these answers a question they would
 * otherwise have to ask by hand.
 */

export function ExplainNumber({
  value,
  children,
  title,
}: {
  value: string;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <span className="inline-flex items-center justify-end gap-1 tabular-nums">
      <span>{value}</span>
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            title={title}
            aria-label={title}
            className="text-muted-foreground/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          >
            <Info className="size-3.5" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
            {children}
          </PopoverContent>
        </PopoverPortal>
      </Popover>
    </span>
  );
}

function DrillHeader({ title }: { title: string }) {
  return <div className="border-b px-3 py-2 text-xs font-semibold">{title}</div>;
}

/** A short two-line skeleton for a drill that's still loading its working. */
function DrillLoading() {
  return (
    <div className="space-y-1.5 px-3 py-3" aria-label="Loading breakdown">
      <Skeleton className="h-3.5 w-full" />
      <Skeleton className="h-3.5 w-4/5" />
      <Skeleton className="h-3.5 w-3/5" />
    </div>
  );
}

/** Net drill - components + the open SOs behind committed (M8-A1). Fetched lazily
 *  from `explain-net` when the popover opens. */
/**
 * Why this row has no cash figure. Two different problems, fixed on two different screens:
 * nobody has ever priced the item, or it is priced in money we hold no rate for. One
 * label would send half of them to the wrong place.
 */
export function costUnavailableReason(row: M8PlanRow): string {
  if (row.unit_cost === null) return 'No supplier cost on record';
  const code = (row.currency || '').trim().toUpperCase();
  return code
    ? `No exchange rate on file for ${code}, so this cost cannot be compared or funded`
    : 'No supplier cost on record';
}

/** The same fact as `costUnavailableReason`, short enough to sit in the cash cell. The
 *  full sentence stays on the cell's title. A bare dash here would read as zero cash. */
export function costUnavailableLabel(row: M8PlanRow): string {
  if (row.unit_cost === null) return 'No cost';
  const code = (row.currency || '').trim().toUpperCase();
  return code ? `No ${code} rate` : 'No cost';
}

export function NetDrill({ row }: { row: M8PlanRow }) {
  const { data: nb, isLoading, isError } = useExplainNet(row.id, true);
  if (isLoading) {
    return (
      <div>
        <DrillHeader title="Net breakdown" />
        <DrillLoading />
      </div>
    );
  }
  if (isError || !nb) {
    return (
      <div>
        <DrillHeader title={`Net = ${fmtSigned(row.net)}`} />
        <p className="px-3 py-2 text-xs text-muted-foreground">Couldn&apos;t load the net breakdown.</p>
      </div>
    );
  }
  return (
    <div>
      <DrillHeader title={`Net = ${fmtSigned(nb.net)}`} />
      <div className="space-y-1 px-3 py-2">
        <div className="flex justify-between">
          <span className="text-muted-foreground">on hand</span>
          <span className="tabular-nums">{fmtInt(nb.on_hand)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">+ on order</span>
          <span className="tabular-nums">{fmtInt(nb.on_order)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">- committed</span>
          <span className="tabular-nums">{fmtInt(nb.committed)}</span>
        </div>
      </div>
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Open sales orders
        </div>
        {nb.committed_sos.length ? (
          <div className="space-y-1">
            {nb.committed_sos.map((so) => (
              <div key={so.so_number} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium">{so.so_number}</span>
                <span
                  className="min-w-0 flex-1 truncate text-muted-foreground"
                  title={so.customer_name ?? undefined}
                >
                  {so.customer_name ?? EM_DASH}
                </span>
                <span className="tabular-nums">{fmtInt(so.qty)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">No open sales orders committed.</div>
        )}
      </div>
    </div>
  );
}

/** Days cover drill - net + demand DOs + CV + the arithmetic (M8-A2/A3). Demand
 *  working is fetched lazily from `explain/demand` when the popover opens. */
export function DaysCoverDrill({ row }: { row: M8PlanRow }) {
  const { data: demand, isLoading, isError } = useExplainDemand(
    row.product_id,
    row.warehouse_id,
    true,
  );
  // Headline avg/day + the "net / rate = days" arithmetic MUST use the SAME rate the
  // engine froze into `days_cover` (`net / forecast_daily_demand = days_cover`), not the
  // live `explain/demand` recompute - that runs a different window (and returns 0 for a
  // network SKU here) which would print "net / 0 = N". The live drill is evidence-only:
  // the DO list + coefficient of variation.
  const frozenRate = row.forecast_daily_demand;
  // No finite cover to show when there's a deficit OR no measurable frozen demand to
  // divide by - either way we must NOT divide by zero.
  const undefinedCover = row.days_cover === null || frozenRate == null || frozenRate <= 0;
  const isDeficit = row.net != null && row.net < 0;
  return (
    <div>
      <DrillHeader
        title={
          undefinedCover
            ? 'Runway = undefined (deficit / no measurable demand)'
            : `Runway = ${fmtInt(row.days_cover)} days`
        }
      />
      {undefinedCover ? (
        <p className="px-3 pt-2 text-xs text-muted-foreground">
          {isDeficit
            ? `Net is a deficit (${fmtSigned(row.net)}), so there is no positive cover to divide by demand - the buy exists to clear the shortfall.`
            : 'No measurable daily demand to divide the net by, so forward cover is undefined.'}
        </p>
      ) : null}
      <div className="space-y-1 px-3 py-2">
        <div className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">Net</div>
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">on hand + on order - committed</span>
          <span className="tabular-nums">{fmtSigned(row.net)}</span>
        </div>
      </div>
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Demand (delivery orders that drove outflow)
        </div>
        {isLoading ? (
          <DrillLoading />
        ) : isError ? (
          <div className="mb-1.5 text-xs text-muted-foreground">Couldn&apos;t load the demand working.</div>
        ) : demand && demand.demand_dos.length ? (
          <div className="mb-1.5 space-y-1">
            {demand.demand_dos.slice(0, 6).map((doItem) => (
              <Link
                key={doItem.order_id}
                href={`/order-management/orders/${doItem.order_id}`}
                className="flex items-center justify-between gap-2 rounded-sm text-xs hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title={`Open ${doItem.do_number}`}
              >
                <span className="font-medium hover:underline">{doItem.do_number}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {doItem.order_date ?? EM_DASH}
                </span>
                <span className="tabular-nums text-muted-foreground">{fmtInt(doItem.qty_out)} out</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="mb-1.5 text-xs text-muted-foreground">No delivery orders in the window.</div>
        )}
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">avg / day (90-day window)</span>
          <span className="tabular-nums">{frozenRate != null ? fmtDecimal(frozenRate) : EM_DASH}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">Coefficient of variation</span>
          <span className="tabular-nums">
            {demand?.demand_cv != null ? fmtDecimal(demand.demand_cv, 2) : EM_DASH}
          </span>
        </div>
        <p className="mt-0.5 text-2xs text-muted-foreground">
          How spread out the weekly demand is - higher means less predictable.
        </p>
      </div>
      {!undefinedCover ? (
        <div className="border-t px-3 py-2 text-xs">
          <span className="tabular-nums">
            {fmtSigned(row.net)} / {fmtDecimal(frozenRate as number)} ={' '}
            <span className="font-semibold">{fmtInt(row.days_cover)} days</span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** Order qty drill - SS / ROP / order-up-to / rounded inputs (M8-A4), plus the
 *  reorder-point formula with its actual inputs (M8-F5). */
export function OrderQtyDrill({
  row,
}: {
  row: M8PlanRow;
}) {
  const q = row.order_qty_inputs;
  // A pooled buy is sized once for every location that shares stock, then split. Saying so
  // is the difference between "why 55" answering itself and the reader doing arithmetic
  // that cannot work.
  const alloc = row.rec.allocation ?? [];
  const pooled = alloc.length > 1;
  const demandRate = row.forecast_daily_demand;
  const leadDays = row.supplier.lead_time_days;
  const line = (label: string, value: number | null) => (
    <div className="flex justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value === null ? EM_DASH : fmtInt(value)}</span>
    </div>
  );
  return (
    <div>
      <DrillHeader title={`Order qty = ${fmtInt(q.rounded_qty)}`} />

      {/* The on-hand offsets panel that used to sit here is GONE. It asked the buyer whether
          to use stock that is already inside the net position, which was never a decision -
          "Use what is on hand at BRW-IB" is arithmetic that has already happened. The real
          choice is buy versus cover from ANOTHER location, and that lives on the row as the
          suggested action. See lib/coverPlan. */}
      <div className="space-y-1 px-3 py-2">
        {line('Safety stock', q.safety_stock)}
        {line('Reorder point', q.reorder_point)}
        {/* On a pooled row the order-up-to belongs to the POOL, not to this bin, so it is
            labelled as such. Otherwise the reader tries order-up-to minus this location's
            net and gets a number that is nowhere on the row. */}
        {line(pooled ? 'Order-up-to level (whole pool)' : 'Order-up-to level', q.order_up_to)}
        {line('MoQ', q.moq)}
        {line('Order multiple', q.order_multiple)}
        <div className="mt-1 flex justify-between border-t pt-1 text-xs font-medium">
          <span>{pooled ? 'This location\u2019s share' : 'Rounded order qty'}</span>
          <span className="tabular-nums">{fmtInt(q.rounded_qty)}</span>
        </div>
      </div>

      {pooled ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Bought for the whole pool
          </div>
          <p className="text-2xs text-muted-foreground">
            One purchase covers {alloc.length} locations that share stock. It is sized once
            against the pool, then placed where the shortage is.
          </p>
          <div className="mt-1 space-y-0.5">
            {alloc.map((a) => (
              <div key={a.warehouse_code ?? String(a.qty)} className="flex justify-between text-2xs">
                <span
                  className={
                    a.warehouse_code === row.rec.warehouse_code
                      ? 'font-medium'
                      : 'text-muted-foreground'
                  }
                >
                  {a.warehouse_code ?? EM_DASH}
                </span>
                <span className="tabular-nums">{fmtInt(a.qty)}</span>
              </div>
            ))}
            <div className="mt-1 flex justify-between border-t pt-1 text-2xs font-medium">
              <span>Pool total</span>
              <span className="tabular-nums">
                {fmtInt(alloc.reduce((t, a) => t + (a.qty ?? 0), 0))}
              </span>
            </div>
          </div>
        </div>
      ) : null}
      {/* Where the daily rate comes from, and how many days of it are being bought. Both
          were invisible: the row showed "1.0/day" with no way to see the deliveries behind
          it, and an order-up-to with no way to see it was 51 days of cover. */}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Order-up-to level
        </div>
        <p className="text-2xs text-muted-foreground">
          S = reorder point + demand rate x review period
        </p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          <span className="tabular-nums text-muted-foreground">
            {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)} +{' '}
            {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x{' '}
            {fmtInt(row.rec.review_days ?? null)}d review
          </span>
          <span className="tabular-nums font-semibold">
            {q.order_up_to === null ? EM_DASH : fmtInt(q.order_up_to)}
          </span>
        </div>
        {row.rec.safety_days != null && row.rec.review_days != null ? (
          <p className="mt-1 text-2xs text-muted-foreground">
            {fmtInt(
              (row.rec.safety_days ?? 0) + (leadDays ?? 0) + (row.rec.review_days ?? 0),
            )}{' '}
            days of cover ({fmtInt(row.rec.safety_days)} safety + {fmtInt(leadDays)} lead +{' '}
            {fmtInt(row.rec.review_days)} review)
          </p>
        ) : null}
      </div>

      {demandRate != null && row.rec.demand_window_days ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Where the rate comes from
          </div>
          <p className="text-2xs text-muted-foreground">
            {fmtInt(demandRate * row.rec.demand_window_days)} units left this location over
            the last {fmtInt(row.rec.demand_window_days)} days, which averages{' '}
            {fmtDecimal(demandRate)} a day. Past deliveries, not the open orders.
          </p>
        </div>
      ) : null}

      {/* Reorder-point explain (M8-F5): the formula + the frozen inputs behind it. */}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Reorder point
        </div>
        <p className="text-2xs text-muted-foreground">
          ROP = safety stock + demand rate x lead time
        </p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          <span className="tabular-nums text-muted-foreground">
            {/* One decimal, so the sum shown equals the answer shown. Rounding safety stock
                to a whole number printed "7 + 1.0/day x 14d = 22", which is off by one and
                reads as a broken calculation. */}
            {q.safety_stock === null ? EM_DASH : fmtDecimal(q.safety_stock)} +{' '}
            {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x{' '}
            {fmtInt(leadDays)}d lead
          </span>
          <span className="tabular-nums font-semibold">
            {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)}
          </span>
        </div>
      </div>
    </div>
  );
}
