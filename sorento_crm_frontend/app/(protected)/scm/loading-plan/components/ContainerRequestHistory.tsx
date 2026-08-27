'use client';

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
  project: { bar: 'bg-sky-500', text: 'text-sky-700', fill: 'text-sky-500' },
  retail: { bar: 'bg-slate-400', text: 'text-slate-600', fill: 'text-slate-400' },
} as const;

/** Twelve bars in a 48x14 box: the year's shape at a glance, each series against its own peak. */
function Sparkline({
  series,
  kind,
}: {
  series: ContainerRequestHistorySeries;
  kind: 'project' | 'retail';
}) {
  const scale = Math.max(...series.months.map((p) => p.qty), 0);
  const w = 3;
  const gap = 1;
  const h = 14;
  return (
    <svg
      width={series.months.length * (w + gap)}
      height={h}
      className={cn('shrink-0', SERIES_PAINT[kind].fill)}
      aria-hidden
      data-testid={`history-spark-${kind}`}
    >
      {series.months.map((point, i) => {
        const bar = scale > 0 ? Math.max(Math.round((point.qty / scale) * h), point.qty > 0 ? 1 : 0) : 0;
        const peak = point.month === series.peak_month && point.qty > 0;
        return (
          <rect
            key={point.month}
            x={i * (w + gap)}
            y={h - bar}
            width={w}
            height={bar}
            opacity={peak ? 1 : 0.5}
            fill="currentColor"
          />
        );
      })}
    </svg>
  );
}

/**
 * The grid cell: per series, the twelve-month TOTAL and a sparkline, the peak in the hover
 * (captain, 27 Aug: the peak-month text was hard to read). The total is the figure a buyer
 * compares against the ask; the sparkline says whether it arrived in one month or twelve.
 */
export function ContainerRequestHistoryCell({
  history,
  loading,
}: {
  history: ContainerRequestHistoryProduct | undefined;
  loading: boolean;
}) {
  if (loading && !history) {
    return <span className="text-2xs text-muted-foreground">Loading</span>;
  }
  if (!history) return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;

  const { project, retail } = history;
  if (project.total === 0 && retail.total === 0) {
    return <span className="text-2xs text-muted-foreground">No orders in 12 months</span>;
  }

  return (
    <div className="flex flex-col gap-0.5 text-2xs">
      {(['project', 'retail'] as const).map((kind) => {
        const series = history[kind];
        const peak = series.peak_month
          ? `peak ${monthLabel(series.peak_month)} ${fmtInt(series.peak_qty)}`
          : 'no orders';
        return (
          <span
            key={kind}
            className={cn('flex items-center gap-1.5 tabular-nums', SERIES_PAINT[kind].text)}
            title={`${kind === 'project' ? 'Project' : 'Retail'} ${fmtInt(series.total)} in 12 months, ${peak}`}
          >
            <span className="w-3 font-medium">{kind === 'project' ? 'P' : 'R'}</span>
            <span className="w-10 text-right">{fmtInt(series.total)}</span>
            <Sparkline series={series} kind={kind} />
          </span>
        );
      })}
    </div>
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
