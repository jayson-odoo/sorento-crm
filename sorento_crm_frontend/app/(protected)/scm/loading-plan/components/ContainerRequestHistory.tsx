'use client';

import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import type {
  ContainerRequestHistoryProduct,
  ContainerRequestHistorySeries,
} from '../../services/fulfilmentService';

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** `2026-04` reads `Apr 26`. The bucket is a month, so it is never rendered as a date. */
export function monthLabel(month: string | null): string {
  if (!month) return EM_DASH;
  const [year, m] = month.split('-');
  const name = MONTHS[Number(m) - 1];
  if (!name || !year) return month;
  return `${name} ${year.slice(2)}`;
}

/** Project is the channel this business plans around; retail is read beside it, never instead. */
const SERIES_PAINT = {
  project: { bar: 'bg-sky-500', text: 'text-sky-700' },
  retail: { bar: 'bg-slate-400', text: 'text-slate-600' },
} as const;

/**
 * The grid cell, one per series (captain, 27 Aug): the peak month and its quantity, and a
 * click opens that series' twelve bars. Peak, not total, because the question is "how big
 * does this product get in a month" (AC-B6); the trend is one click away rather than crammed
 * beside the figure.
 */
export function ContainerRequestHistoryPeakCell({
  history,
  loading,
  kind,
}: {
  history: ContainerRequestHistoryProduct | undefined;
  loading: boolean;
  kind: 'project' | 'retail';
}) {
  if (loading && !history) {
    return <span className="text-2xs text-muted-foreground">Loading</span>;
  }
  if (!history) return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;
  const series = history[kind];
  if (series.total === 0 || !series.peak_month) {
    return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;
  }
  const label = kind === 'project' ? 'Project' : 'Retail';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={`${label} ordered, last 12 months`}
          className={cn(
            'inline-flex items-baseline gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
            SERIES_PAINT[kind].text,
          )}
        >
          <span>{fmtInt(series.peak_qty)}</span>
          <span className="text-2xs text-muted-foreground">{monthLabel(series.peak_month)}</span>
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80" align="end">
          <p className="mb-2 text-xs font-medium">{label} ordered qty (SO booked), last 12 months</p>
          <SeriesBars series={series} kind={kind} />
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function SeriesBars({
  series,
  kind,
}: {
  series: ContainerRequestHistorySeries;
  kind: 'project' | 'retail';
}) {
  const paint = SERIES_PAINT[kind];
  // Each series is drawn against ITS OWN peak. A shared scale is more honest arithmetic and
  // worse reading: retail runs at a tenth of project here, so one scale flattens the retail
  // year into a line and hides the shape - which is the only thing a bar adds over the
  // figures already printed under it.
  const scale = Math.max(...series.months.map((p) => p.qty), 0);
  return (
    <div data-testid={`history-series-${kind}`}>
      <div className="flex items-end gap-1" style={{ height: 56 }}>
        {series.months.map((point) => {
          const height = scale > 0 ? Math.round((point.qty / scale) * 100) : 0;
          const peak = point.month === series.peak_month && point.qty > 0;
          return (
            <span
              key={point.month}
              data-testid={`history-bar-${kind}-${point.month}`}
              title={`${monthLabel(point.month)} ${fmtInt(point.qty)}`}
              className="flex min-w-0 flex-1 flex-col justify-end"
              style={{ height: '100%' }}
            >
              <span
                className={cn(
                  'w-full rounded-t-sm',
                  paint.bar,
                  peak ? 'opacity-100' : 'opacity-60',
                )}
                style={{ height: `${Math.max(height, point.qty > 0 ? 3 : 1)}%` }}
              />
            </span>
          );
        })}
      </div>
      <div className="mt-1 flex gap-1 text-[10px] text-muted-foreground">
        {series.months.map((point) => (
          <span key={point.month} className="min-w-0 flex-1 text-center">
            {monthLabel(point.month).slice(0, 1)}
          </span>
        ))}
      </div>
      <p className={cn('mt-1 text-xs tabular-nums', paint.text)}>
        {kind === 'project' ? 'Project' : 'Retail'}{' '}
        {series.peak_month
          ? `peak ${monthLabel(series.peak_month)} ${fmtInt(series.peak_qty)}`
          : 'no orders'}
        {' · '}avg {fmtInt(Math.round(series.avg))} · total {fmtInt(series.total)}
      </p>
    </div>
  );
}

/**
 * Both series, twelve zero-filled buckets each (AC-B7).
 *
 * Zero-filled on purpose: a month with no order is a fact about the product, and a chart that
 * silently skips it turns four scattered orders into a solid year.
 */
export function ContainerRequestHistoryBars({
  history,
  loading,
}: {
  history: ContainerRequestHistoryProduct | undefined;
  loading: boolean;
}) {
  if (!history) {
    return (
      <p className="text-xs text-muted-foreground">
        {loading ? 'Loading the last 12 months...' : 'No order history loaded.'}
      </p>
    );
  }
  if (history.project.total === 0 && history.retail.total === 0) {
    return <p className="text-xs text-muted-foreground">No orders in the last 12 months.</p>;
  }
  return (
    <div className="space-y-3">
      <SeriesBars series={history.project} kind="project" />
      <SeriesBars series={history.retail} kind="retail" />
    </div>
  );
}
