'use client';

import { Progress } from '@/components/ui/progress';
import { fmtTrimmedDecimal } from '../../../lib/format';

/**
 * How full the container is, against the size this invoice is being fitted into (AC-D2).
 *
 * Over capacity is stated in the same sentence rather than only coloured, because the
 * number Ms Tee acts on is "how much has to come off", not "it is red". Lines carrying no
 * volume are counted out loud for the same reason: a fill of 41 cbm computed from half the
 * lines is not 41 cbm, and silently rounding that away is how a container is planned twice.
 */
export function ProformaVolumeFill({
  totalCbm,
  containerCbm,
  containerLabel,
  unmeasuredLines,
  className,
}: {
  totalCbm: number | null;
  containerCbm: number | null;
  containerLabel: string | null;
  unmeasuredLines: number;
  className?: string;
}) {
  const measured = totalCbm ?? 0;
  const capacity = containerCbm && containerCbm > 0 ? containerCbm : null;
  const pct = capacity ? (measured / capacity) * 100 : null;
  const over = capacity && measured > capacity ? measured - capacity : null;

  return (
    <div className={className}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-sm font-medium">
          {totalCbm === null
            ? 'No volume on this invoice'
            : `${fmtTrimmedDecimal(measured, 2)} cbm`}
        </span>
        {capacity ? (
          <span className="text-xs text-muted-foreground">
            of {fmtTrimmedDecimal(capacity, 2)}
            {containerLabel ? ` (${containerLabel})` : ''}
            {pct !== null ? ` - ${fmtTrimmedDecimal(pct, 0)}% full` : ''}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">no container size on file</span>
        )}
        {over ? (
          <span className="text-xs font-medium text-rose-600">
            over by {fmtTrimmedDecimal(over, 2)} cbm
          </span>
        ) : null}
      </div>
      <Progress
        className="mt-1.5 h-2"
        value={pct === null ? 0 : Math.min(pct, 100)}
        indicatorClassName={over ? 'bg-rose-500' : 'bg-emerald-500'}
        aria-label="Container fill"
      />
      {unmeasuredLines > 0 ? (
        <p className="mt-1 text-2xs text-muted-foreground">
          {unmeasuredLines} unmeasured {unmeasuredLines === 1 ? 'line' : 'lines'}
        </p>
      ) : null}
    </div>
  );
}

export default ProformaVolumeFill;
