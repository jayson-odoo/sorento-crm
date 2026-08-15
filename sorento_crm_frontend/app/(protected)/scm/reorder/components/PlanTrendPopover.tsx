'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import type { ApexOptions } from 'apexcharts';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { fmtDate, fmtInt, fmtSupplierCost } from '../../lib/format';
import { useCustomerOrders } from '../hooks/useReorderRun';
import {
  TRAJECTORY_ROW_LABEL,
  TRAJECTORY_TONE,
  chartSeries,
  describeTrajectory,
  describeYearAgo,
  type TrajectoryCustomer,
  type TrajectoryEntry,
} from '../lib/trajectory';

const ApexChart = dynamic(() => import('react-apexcharts').then((mod) => mod.default), {
  ssr: false,
});

/**
 * The trend behind the quantity suggestion: a line graph first, then the receipts.
 *
 * > "i need this kind of trend to be in a line graph so it is easier to relate"
 *
 * Two lines: this year's months, and the SAME months a year earlier (dashed), so the eye
 * compares seasons vertically - the "both, side by side" the user chose. Beneath it, who
 * bought the product; who SOLD it is named absent because the order book carries no
 * salesperson, and inventing one would be worse than admitting the gap.
 */

const TONE_CLASS = {
  ok: 'text-green-600',
  neutral: 'text-muted-foreground',
  warning: 'text-amber-600',
} as const;

/**
 * The orders behind ONE customer row, fetched when the row is opened.
 *
 * > "sells RM 0.94?"
 *
 * A quantity beside a name says who buys it; it does not say at what price, and that is
 * the question the row is opened to answer. Newest first, capped, with the count of what
 * is not shown said out loud rather than silently dropped.
 */
function CustomerOrderLines({
  runId,
  productId,
  segment,
  customerKey,
}: {
  runId: string | null;
  productId: string | null;
  segment: string;
  customerKey: string;
}) {
  const { data, isLoading, isError, error } = useCustomerOrders(
    runId,
    productId,
    segment,
    customerKey,
    true,
  );

  if (isLoading) {
    return (
      <div className="space-y-1 py-1">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    );
  }
  if (isError) {
    return (
      <p className="py-1 text-2xs text-muted-foreground">
        {error instanceof Error ? error.message : 'Failed to load the orders.'}
      </p>
    );
  }
  if (!data || !data.lines.length) {
    return <p className="py-1 text-2xs text-muted-foreground">No orders in the window.</p>;
  }
  return (
    <div className="py-1">
      <table className="w-full text-2xs">
        <tbody>
          {data.lines.map((l, i) => (
            <tr key={`${l.so_number}-${i}`}>
              <td className="max-w-32 truncate py-0.5" title={l.so_number}>
                {l.so_number}
              </td>
              <td className="py-0.5 text-right tabular-nums">{fmtDate(l.order_date)}</td>
              <td className="py-0.5 text-right tabular-nums">{fmtInt(l.qty)}</td>
              <td className="py-0.5 text-right tabular-nums">
                {fmtSupplierCost(l.unit_price, null)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.total > data.shown ? (
        <p className="pt-0.5 text-2xs text-muted-foreground">
          {fmtInt(data.total - data.shown)} more
        </p>
      ) : null}
    </div>
  );
}

/** One Who-bought-it row: the summary, and the orders behind it on request. */
function CustomerRow({
  customer,
  runId,
  productId,
  segment,
}: {
  customer: TrajectoryCustomer;
  runId: string | null;
  productId: string | null;
  segment: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td className="max-w-40 truncate py-0.5" title={customer.customer_name}>
          <button
            type="button"
            aria-expanded={open}
            className="flex w-full items-center gap-1 text-left hover:text-foreground"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? (
              <ChevronDown className="size-3 shrink-0" aria-hidden />
            ) : (
              <ChevronRight className="size-3 shrink-0" aria-hidden />
            )}
            <span className="truncate">{customer.customer_name}</span>
          </button>
        </td>
        <td className="py-0.5 text-right tabular-nums">{fmtInt(customer.qty)}</td>
        <td className="py-0.5 text-right tabular-nums">{fmtDate(customer.last_order_date)}</td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={3} className="pl-4">
            <CustomerOrderLines
              runId={runId}
              productId={productId}
              segment={segment}
              customerKey={customer.customer_key}
            />
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function PlanTrendPopover({
  trend,
  sellingPrice,
  runId = null,
  productId = null,
  segment = 'project',
  outstandingSales = null,
}: {
  trend: TrajectoryEntry | undefined;
  /** What this line sells for (realized average, or list price when nothing has sold) -
   *  the same figure the health popover already carries, threaded here rather than
   *  refetched (user markup, 2026-08-12: "similar to SO - what is the trend of purchase").
   *  Omitted when we hold no opinion. */
  sellingPrice?: number | null;
  /** The run + product + side the customer drill is keyed by. */
  runId?: string | null;
  productId?: string | null;
  segment?: string;
  /** This row's open sales-order quantity. A product can carry real open demand and no
   *  dated history at all (the outstanding book only started stating an order date), and
   *  "No order history" beside 51 open units reads as a defect rather than as a fact. */
  outstandingSales?: number | null;
}) {
  if (!trend) {
    return (
      <span className="block text-2xs text-muted-foreground">
        <span className="block truncate" title="No orders dated in the last 24 months.">
          No orders dated in the last 24 months.
        </span>
        {outstandingSales && outstandingSales > 0 ? (
          <span className="block truncate">Open now: {fmtInt(outstandingSales)} (see Demand)</span>
        ) : null}
      </span>
    );
  }

  const { labels, thisYear, lastYear } = chartSeries(trend);
  const hasLastYear = lastYear.some((v) => v !== null);

  const options: ApexOptions = {
    chart: { type: 'line', toolbar: { show: false }, zoom: { enabled: false } },
    stroke: { curve: 'smooth', width: [2.5, 2], dashArray: [0, 5] },
    colors: ['var(--color-primary, #2563eb)', '#94a3b8'],
    xaxis: { categories: labels, labels: { style: { fontSize: '10px' } } },
    yaxis: { labels: { style: { fontSize: '10px' } } },
    legend: { fontSize: '11px' },
    grid: { strokeDashArray: 3 },
    tooltip: { y: { formatter: (v: number) => (v === null ? 'no data' : String(v)) } },
  };
  const series = [
    { name: 'This year', data: thisYear },
    ...(hasLastYear ? [{ name: 'Last year', data: lastYear }] : []),
  ];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'block truncate text-left text-2xs underline decoration-dotted underline-offset-2',
            TONE_CLASS[TRAJECTORY_TONE[trend.verdict]],
          )}
          aria-label="Order trend"
        >
          {TRAJECTORY_ROW_LABEL[trend.verdict]}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-96 max-w-[92vw] text-xs" align="start">
          <p className="font-medium text-foreground">{describeTrajectory(trend)}</p>
          <p className="mt-1 text-muted-foreground">{describeYearAgo(trend)}</p>

          <div className="mt-2 -mx-1">
            <ApexChart options={options} series={series} type="line" height={160} />
          </div>

          {sellingPrice != null ? (
            <p className="mt-2 text-muted-foreground">
              Selling price {fmtSupplierCost(sellingPrice, null)}
            </p>
          ) : null}

          <div className="mt-2">
            <p className="font-medium text-foreground">Who bought it</p>
            {trend.customers.length ? (
              <table className="mt-0.5 w-full text-muted-foreground">
                <thead>
                  <tr className="text-2xs uppercase text-muted-foreground/70">
                    <th className="pb-0.5 text-left font-normal">Customer</th>
                    <th className="pb-0.5 text-right font-normal">Qty</th>
                    <th className="pb-0.5 text-right font-normal">Last order</th>
                  </tr>
                </thead>
                <tbody>
                  {trend.customers.map((c) => (
                    <CustomerRow
                      key={`${c.customer_key ?? ''}:${c.customer_name}`}
                      customer={c}
                      runId={runId}
                      productId={productId}
                      segment={segment}
                    />
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-muted-foreground">No orders in the window.</p>
            )}
          </div>

          {/* Absent, never invented: the order book carries no salesperson. */}
          {!trend.agents_available ? (
            <p className="mt-2 text-2xs text-muted-foreground">
              Who sold it is not in the order data yet.
            </p>
          ) : null}

          <p className="mt-2 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own orders only.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
