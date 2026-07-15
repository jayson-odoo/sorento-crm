'use client';

import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { fmtInt } from '../lib/format';
import { xyzLabel } from '../lib/health';
import { useDemandSeries } from '../hooks/useScmDashboard';
import type { XyzClass } from '../types/scm.types';

/**
 * Per-SKU demand trend sparkline. Fetches ~12 MONTHLY buckets of real DO outflow
 * (`/dashboard/demand-series`) when the Product row is expanded — the shape now
 * reflects live data. Dependency-free inline SVG, theme-aware via `currentColor`;
 * reinforced by the plain-language Demand-class caption. No animation
 * (reduced-motion friendly). Rendered above the per-warehouse breakdown.
 */
export function DemandTrendLine({
  sku,
  warehouse,
  demandClass,
  className,
}: {
  sku: string;
  /** Warehouse scope, or null to aggregate across all warehouses (product view). */
  warehouse?: string | null;
  /** Demand-variability class for the caption (falls back to the fetched class). */
  demandClass: XyzClass | null;
  className?: string;
}) {
  const { data, isLoading, isError } = useDemandSeries(sku, warehouse ?? null, true);

  const classLabel = xyzLabel(demandClass ?? data?.xyz_class ?? null);

  const header = (
    <div className="mb-1 flex items-center justify-between gap-2">
      <span className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">
        Demand — last 12 months
      </span>
      <span className="text-2xs text-muted-foreground">{classLabel}</span>
    </div>
  );

  if (isLoading) {
    return (
      <div className={cn('text-primary', className)}>
        {header}
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className={cn('text-primary', className)}>
        {header}
        <div className="py-3 text-2xs text-scm-stockout">Couldn&apos;t load the demand trend.</div>
      </div>
    );
  }

  const points = data?.points ?? [];
  const peak = data?.peak_qty ?? 0;
  const n = points.length;

  // No outflow across the whole window → nothing to plot; show an explicit note.
  if (!n || peak <= 0) {
    return (
      <div className={cn('text-primary', className)}>
        {header}
        <div className="py-3 text-2xs text-muted-foreground">
          No sales outflow in the last 12 months.
        </div>
      </div>
    );
  }

  // viewBox units — stretched to the container width (preserveAspectRatio=none)
  // with a non-scaling stroke so the line stays crisp at any width.
  const W = 320;
  const H = 44;
  const PAD_Y = 4;
  const innerH = H - PAD_Y * 2;
  const max = peak || 1;

  const x = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
  const y = (v: number) => PAD_Y + innerH - (v / max) * innerH;

  const linePoints = points.map((p, i) => `${x(i)},${y(p.qty)}`).join(' ');
  const areaPoints = `${x(0)},${H} ${linePoints} ${x(n - 1)},${H}`;

  const first = points[0]?.month ?? '';
  const last = points[n - 1]?.month ?? '';

  return (
    <div className={cn('text-primary', className)}>
      {header}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-12 w-full"
        role="img"
        aria-label={`Demand trend over 12 months — ${classLabel}, peak ${fmtInt(peak)} per month`}
      >
        <polygon points={areaPoints} className="fill-current opacity-10" />
        <polyline
          points={linePoints}
          fill="none"
          className="stroke-current"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="mt-1 flex items-center justify-between text-2xs tabular-nums text-muted-foreground">
        <span>{first}</span>
        <span className="text-muted-foreground/70">peak {fmtInt(peak)}/mo</span>
        <span>{last}</span>
      </div>
    </div>
  );
}
