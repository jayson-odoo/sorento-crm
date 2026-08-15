'use client';

import dynamic from 'next/dynamic';
import type { ApexOptions } from 'apexcharts';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { fmtDate, fmtInt, fmtSupplierCost } from '../../lib/format';
import {
  TRAJECTORY_ROW_LABEL,
  TRAJECTORY_TONE,
  chartSeries,
  describeTrajectory,
  describeYearAgo,
  type TrajectoryEntry,
} from '../lib/trajectory';

/**
 * A customer row, widened with `last_order_date` (backend: `trajectory_service.py`).
 *
 * The shared `TrajectoryEntry['customers']` element type does not carry this field yet -
 * kept as a local widening here rather than edited into `lib/trajectory.ts` while that
 * file is in flight elsewhere. Structurally compatible: the backend payload already
 * includes it, so this is purely a read-side type, no runtime cast of substance.
 */
type CustomerRow = TrajectoryEntry['customers'][number] & { last_order_date?: string | null };

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

export function PlanTrendPopover({
  trend,
  sellingPrice,
}: {
  trend: TrajectoryEntry | undefined;
  /** What this line sells for (realized average, or list price when nothing has sold) -
   *  the same figure the health popover already carries, threaded here rather than
   *  refetched (user markup, 2026-08-12: "similar to SO - what is the trend of purchase").
   *  Omitted when we hold no opinion. */
  sellingPrice?: number | null;
}) {
  if (!trend) {
    return <span className="text-2xs text-muted-foreground">No order history</span>;
  }

  const { labels, thisYear, lastYear } = chartSeries(trend);
  const hasLastYear = lastYear.some((v) => v !== null);

  // Read the chart, not squint at it. At 12 months in a 24rem popover the month labels
  // collided and the y axis printed a tick per gridline in fractions of a unit, which is
  // meaningless for a quantity; the legend also sat under the plot, stealing height from
  // the only thing worth looking at.
  const options: ApexOptions = {
    chart: { type: 'line', toolbar: { show: false }, zoom: { enabled: false } },
    stroke: { curve: 'smooth', width: [2.5, 2], dashArray: [0, 5] },
    colors: ['var(--color-primary, #2563eb)', '#94a3b8'],
    xaxis: {
      categories: labels,
      labels: { rotate: -45, hideOverlappingLabels: true, style: { fontSize: '10px' } },
    },
    yaxis: {
      min: 0,
      tickAmount: 4,
      labels: { formatter: (v: number) => fmtInt(v), style: { fontSize: '10px' } },
    },
    legend: { position: 'top', horizontalAlign: 'left', fontSize: '11px' },
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
        <PopoverContent className="w-[30rem] max-w-[92vw] text-xs" align="start">
          <p className="font-medium text-foreground">{describeTrajectory(trend)}</p>
          <p className="mt-1 text-muted-foreground">{describeYearAgo(trend)}</p>

          {/* The app-wide Metronic sheet stacks every Apex legend vertically
              (`css/components/apexcharts.css`), which here costs two lines of chart height
              for two words. Overridden for this chart only, not globally. */}
          <div className="mt-2 -mx-1 [&_.apexcharts-legend]:flex-row [&_.apexcharts-legend]:flex-wrap [&_.apexcharts-legend]:items-center [&_.apexcharts-legend]:gap-x-4">
            <ApexChart options={options} series={series} type="line" height={240} />
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
                  {(trend.customers as CustomerRow[]).map((c) => (
                    <tr key={c.customer_name}>
                      <td className="max-w-40 truncate py-0.5" title={c.customer_name}>
                        {c.customer_name}
                      </td>
                      <td className="py-0.5 text-right tabular-nums">{c.qty.toLocaleString()}</td>
                      <td className="py-0.5 text-right tabular-nums">{fmtDate(c.last_order_date)}</td>
                    </tr>
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
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
