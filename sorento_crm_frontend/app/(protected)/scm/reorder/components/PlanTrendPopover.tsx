'use client';

import dynamic from 'next/dynamic';
import type { ApexOptions } from 'apexcharts';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import {
  TRAJECTORY_ROW_LABEL,
  TRAJECTORY_TONE,
  chartSeries,
  describeTrajectory,
  describeYearAgo,
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

export function PlanTrendPopover({ trend }: { trend: TrajectoryEntry | undefined }) {
  if (!trend) {
    return <span className="text-2xs text-muted-foreground">No order history</span>;
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

          <div className="mt-2">
            <p className="font-medium text-foreground">Who bought it</p>
            {trend.customers.length ? (
              <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                {trend.customers.map((c) => (
                  <li key={c.customer_name} className="flex justify-between gap-2">
                    <span className="truncate">{c.customer_name}</span>
                    <span className="tabular-nums">{c.qty.toLocaleString()}</span>
                  </li>
                ))}
              </ul>
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
