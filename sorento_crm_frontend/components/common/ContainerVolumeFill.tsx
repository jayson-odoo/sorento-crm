'use client';

import { Progress } from '@/components/ui/progress';

/** A number to AT MOST `dp` decimals, trailing zeros trimmed - "65" not "65.00". Local
 *  rather than imported: the gauge is shared across features and a feature-scoped
 *  formatter would pull this shared component back into that feature's own lib. */
function fmtTrimmedDecimal(value: number | null | undefined, dp = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return Number(value.toFixed(dp)).toLocaleString('en-MY', { maximumFractionDigits: dp });
}

/**
 * How full a container is, against the size it is being loaded into (S5, ruling 1).
 *
 * Moved here from the proforma-invoice feature (`ProformaVolumeFill`, same props) because
 * capacity is a property of the CONTAINER, not any one document that fed it: a packing list
 * routinely consolidates several proforma invoices, so the gauge belongs on the shipment the
 * convert dialog creates, not on an invoice beneath it.
 *
 * Over capacity is stated in the same sentence rather than only coloured, because the number
 * a person acts on is "how much has to come off", not "it is red". Lines carrying no volume
 * are counted out loud for the same reason: a fill of 41 cbm computed from half the lines is
 * not 41 cbm, and silently rounding that away is how a container is planned twice.
 */
export function ContainerVolumeFill({
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
            ? 'No volume on file'
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

export default ContainerVolumeFill;
