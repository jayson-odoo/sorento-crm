'use client';

import { AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  HEALTH_STATES,
  M1_ACTIVE_STATES,
  abcLabel,
  healthMeta,
  xyzLabel,
} from '../lib/health';
import type { AbcClass, HealthState, XyzClass } from '../types/scm.types';

/** Canonical formula copy - reused by the grid header + the drill-down popup. */
export const NET_POSITION_FORMULA = 'Net position = On hand + On order − Committed';

/** Canonical days-of-cover formula copy (M2). */
export const DAYS_OF_COVER_FORMULA = 'Days of cover = Net position ÷ Avg daily demand';

/** Keyboard-accessible info tooltip explaining the Net-position formula. Sits on
 *  the "Net position" column header in both the Product grid and the popup. */
export function NetPositionInfo({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          role="img"
          aria-label={NET_POSITION_FORMULA}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            'inline-flex cursor-help items-center text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            className,
          )}
        >
          <Info className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>{NET_POSITION_FORMULA}</TooltipContent>
    </Tooltip>
  );
}

/** Canonical avg-daily-demand explainer copy (M8-B9). */
export const AVG_DAILY_DEMAND_HINT =
  'Mean units shipped per day over the demand window';

/** Canonical reorder-point formula copy (M8-F5). Plain "x" (not a math sign). */
export const REORDER_POINT_FORMULA =
  'Reorder point = Safety stock + Demand rate x Lead time';

/** Plain-language definitions of the two ROP inputs (M8-F10), shown beside their
 *  values in the reorder-point explain. Shared so the reorder-page order-qty drill
 *  can import the same copy. */
export const SAFETY_STOCK_HINT =
  'Buffer stock for demand/supply variability over the lead time.';
export const LEAD_TIME_HINT = 'Days from placing a PO to receiving the goods.';

/** Info tooltip for the Avg-daily-demand column header (mirrors NetPositionInfo). */
export function AvgDemandInfo({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          role="img"
          aria-label={AVG_DAILY_DEMAND_HINT}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            'inline-flex cursor-help items-center text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            className,
          )}
        >
          <Info className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>{AVG_DAILY_DEMAND_HINT}</TooltipContent>
    </Tooltip>
  );
}

/** Info tooltip for the Days-of-cover column header (mirrors NetPositionInfo). */
export function DaysOfCoverInfo({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          role="img"
          aria-label={DAYS_OF_COVER_FORMULA}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            'inline-flex cursor-help items-center text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            className,
          )}
        >
          <Info className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>{DAYS_OF_COVER_FORMULA}</TooltipContent>
    </Tooltip>
  );
}

/** Plain-language class chip. `kind='abc'` renders the "Value" scale
 *  (High/Med/Low), `kind='xyz'` the "Demand" scale (Steady/Variable/Erratic) -
 *  the underlying A/B/C · X/Y/Z values stay internal (see lib/health display
 *  maps). `null` (unclassifiable SKU) reads as a muted "Unknown" so the column
 *  never fabricates a class. `kind` tints the chip so the two read apart. */
export function ClassChip({
  value,
  kind,
  className,
}: {
  value: string | null;
  kind: 'abc' | 'xyz';
  className?: string;
}) {
  const unknown = !value;
  const label =
    kind === 'abc' ? abcLabel(value as AbcClass | null) : xyzLabel(value as XyzClass | null);
  const scale = kind === 'abc' ? 'Value' : 'Demand';
  const tip = unknown
    ? kind === 'abc'
      ? 'Value not available (no cost on file)'
      : 'Demand pattern not available'
    : `${scale}: ${label}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            'inline-flex items-center justify-center rounded px-1.5 py-0.5 text-2xs font-semibold',
            unknown
              ? 'bg-muted text-muted-foreground'
              : kind === 'abc'
                ? 'bg-primary/10 text-primary'
                : 'bg-muted text-foreground/70',
            className,
          )}
          aria-label={`${scale}: ${label}`}
        >
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

/** Composite-vs-confidence explainer for the supplier scorecard tooltip. Confidence
 *  = how MANY receipts back the score (sample size); the composite = how WELL those
 *  receipts performed. A thin sample (below the 3-order minimum) reads as provisional
 *  even when its composite is high - the two axes are independent. `sampleSize` is
 *  woven in when known so the copy is concrete rather than generic. */
function confidenceTip(
  confidence: 'high' | 'medium' | 'low',
  sampleSize?: number,
): string {
  const has = sampleSize != null;
  const n = sampleSize ?? 0;
  const orders = has ? `${n} order${n === 1 ? '' : 's'} scored` : 'The orders scored';
  if (confidence === 'low') {
    return (
      `Confidence reflects how many receipts back the score. ` +
      `${orders}${has ? ' - below the 3-order minimum' : ' fall below the 3-order minimum'}, ` +
      `so treat it as provisional. The composite is how well those receipts performed, ` +
      `not how sure we are of it.`
    );
  }
  return (
    `Confidence reflects how many receipts back the score. ` +
    `${orders} - enough history to trust it. The composite is how well those ` +
    `receipts performed, a separate axis from confidence.`
  );
}

/** Confidence badge for the supplier scorecard. `low` is deliberately loud +
 *  distinct (amber, outlined, explanatory) so a thin sample is never mistaken
 *  for a confident score (plan §6 - don't oversell thin data). The badge is the
 *  trigger for a keyboard-accessible tooltip explaining the composite-vs-confidence
 *  distinction (and folding in the scored-order count when known). */
export function ConfidenceBadge({
  confidence,
  sampleSize,
  className,
}: {
  confidence: 'high' | 'medium' | 'low';
  sampleSize?: number;
  className?: string;
}) {
  const meta = {
    high: { label: 'High confidence', cls: 'bg-scm-healthy-soft text-scm-healthy' },
    medium: { label: 'Medium confidence', cls: 'bg-muted text-muted-foreground' },
    low: {
      label: 'Low confidence',
      cls: 'border border-scm-low bg-scm-low-soft text-scm-low',
    },
  }[confidence];
  const tip = confidenceTip(confidence, sampleSize);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          role="note"
          aria-label={`${meta.label}. ${tip}`}
          className={cn(
            'inline-flex cursor-help items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            meta.cls,
            className,
          )}
        >
          {confidence === 'low' ? <AlertTriangle className="size-3 shrink-0" aria-hidden /> : null}
          {meta.label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  );
}

/** Status chip: colour tint + icon + label. Colour is never the sole signal. */
export function StateChip({
  state,
  className,
}: {
  state: HealthState;
  className?: string;
}) {
  const meta = healthMeta(state);
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium',
        meta.softClass,
        meta.textClass,
        className,
      )}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      {meta.label}
    </span>
  );
}

/** Critical attention pill - stockout WITH open committed demand. Distinct from
 *  the plain stockout chip (heavier, outlined) so it never relies on colour alone. */
export function CommittedStockoutPill({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-scm-stockout bg-scm-stockout-soft px-2 py-0.5 text-2xs font-semibold text-scm-stockout',
        className,
      )}
      title="Stocked out while customer demand is committed - act first"
    >
      <AlertTriangle className="size-3 shrink-0" aria-hidden />
      committed
    </span>
  );
}

/** Composition mini-bar: relative split of a warehouse's SKUs by health state.
 *  Deferred segments (low/overstock = null) are simply absent - never faked. */
export function CompositionBar({
  composition,
  className,
}: {
  composition: {
    stockout: number;
    dead: number;
    healthy: number;
    incoming: number;
    low: number | null;
    overstock: number | null;
  };
  className?: string;
}) {
  const segments = M1_ACTIVE_STATES.map((state) => ({
    state,
    count: composition[state as keyof typeof composition] as number,
  })).filter((s) => s.count > 0);
  const total = segments.reduce((sum, s) => sum + s.count, 0);

  if (total === 0) {
    return <div className={cn('h-1.5 w-full rounded-full bg-muted', className)} />;
  }

  return (
    <div
      className={cn('flex h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}
      role="img"
      aria-label={segments.map((s) => `${healthMeta(s.state).label}: ${s.count}`).join(', ')}
    >
      {segments.map((s) => (
        <Tooltip key={s.state}>
          <TooltipTrigger asChild>
            <div
              className={cn('h-full', healthMeta(s.state).barClass)}
              style={{ width: `${(s.count / total) * 100}%` }}
            />
          </TooltipTrigger>
          <TooltipContent>
            {healthMeta(s.state).label}: {s.count}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

/** Legend for the health-state ramp. Deferred states are shown greyed with a
 *  "later step" note so the vocabulary is complete but honest (AC-M1.7).
 *
 *  When `onToggle` is supplied the non-deferred chips become filter buttons:
 *  clicking one filters the current perspective to that health status, clicking
 *  the active chip again clears it (aria-pressed reflects the selection). */
export function HealthLegend({
  className,
  activeState,
  onToggle,
}: {
  className?: string;
  activeState?: HealthState | null;
  onToggle?: (state: HealthState) => void;
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-2', className)}>
      {onToggle ? (
        <span className="text-2xs font-medium text-muted-foreground">Filter:</span>
      ) : null}
      {(Object.keys(HEALTH_STATES) as HealthState[]).map((state) => {
        const meta = healthMeta(state);
        const Icon = meta.icon;
        const interactive = !!onToggle && !meta.deferred;
        const active = interactive && activeState === state;
        const content = (
          <>
            <span className={cn('size-2.5 rounded-full', meta.barClass, meta.deferred && 'opacity-40')} />
            <Icon className="size-3" aria-hidden />
            {meta.label}
            {meta.deferred ? <span className="italic">(later step)</span> : null}
          </>
        );

        if (interactive) {
          return (
            <button
              key={state}
              type="button"
              aria-pressed={active}
              onClick={() => onToggle?.(state)}
              title={`Filter to ${meta.label}`}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-2xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                active
                  ? cn(meta.softClass, meta.textClass, 'border-current font-medium')
                  : 'border-transparent text-muted-foreground hover:bg-muted',
              )}
            >
              {content}
            </button>
          );
        }

        return (
          <span
            key={state}
            className={cn(
              'inline-flex items-center gap-1.5 text-2xs',
              meta.deferred ? 'text-muted-foreground/60' : 'text-muted-foreground',
            )}
            title={meta.intent}
          >
            {content}
          </span>
        );
      })}
    </div>
  );
}
