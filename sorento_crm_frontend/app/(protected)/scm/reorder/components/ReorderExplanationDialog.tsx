'use client';

import { useCallback } from 'react';
import {
  AlertTriangle,
  ArrowRightLeft,
  Ban,
  Layers,
  PackageX,
  ShoppingCart,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import RecordNavigation from '@/components/common/RecordNavigation';
import { cn } from '@/lib/utils';
import { xyzLabel } from '../../lib/health';
import type { XyzClass } from '../../types/scm.types';
import { EM_DASH, fmtInt, fmtMoney } from '../../lib/format';
import { ConfidenceBadge } from '../../components/HealthIndicators';
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';

/**
 * Row-click explanation popup — the headline "make it fool-proof" surface.
 *
 * Turns a recommendation's FROZEN inputs (AC-M3.11) into a plain-language,
 * step-by-step derivation a supply-chain novice can follow: it never recomputes
 * on the client, only presents the numbers the deterministic engine already
 * stored (this is NOT the M5 LLM narrator). Every metric is spelled out, the
 * arithmetic is made explicit (ROP = demand × lead time + safety stock, order
 * qty = order-up-to − net), and the modal is mobile-scrollable.
 */

/** Compact number for the arithmetic — trims trailing zeros so 11.0 reads "11". */
function dec(v: number | null | undefined): string {
  if (v === null || v === undefined) return EM_DASH;
  return Number(v.toFixed(2)).toLocaleString('en-MY', { maximumFractionDigits: 2 });
}

const REASON_NOUN: Record<string, string> = {
  reorder_point: 'reorder point',
  min_max: 'minimum level',
  periodic_review: 'order-up-to target',
  dead: 'dead-stock window',
  overstock: 'days-of-cover ceiling',
};

const LEAD_SOURCE_WHY: Record<string, string> = {
  measured: 'measured from past receipts',
  declared: 'declared by the supplier',
  default: 'default (no history on file)',
};

const SS_METHOD_WHY: Record<string, (r: ReorderRecommendation) => string> = {
  fixed_days: (r) => `${dec(r.safety_days)}-day buffer of demand`,
  statistical: (r) =>
    `statistical buffer at ${r.service_level != null ? `${Math.round(r.service_level * 100)}%` : ''} service level`,
  manual: () => 'manual override set on the policy',
};

const POLICY_TYPE_LABEL: Record<string, string> = {
  reorder_point: 'Reorder point',
  min_max: 'Min / Max',
  periodic_review: 'Periodic review',
};

const SELECTION_LABEL: Record<string, string> = {
  primary: 'primary supplier',
  best_score: 'best performance score',
  lowest_cost: 'lowest cost',
};

/** One derivation line: a label, its value, and a short plain-language "why". */
function Step({
  label,
  value,
  why,
  emphasis,
}: {
  label: string;
  value: React.ReactNode;
  why?: React.ReactNode;
  /** Formula steps (ROP, order qty) render boxed so the arithmetic stands out. */
  emphasis?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-0.5 border-b border-border/60 py-2 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4',
        emphasis && 'rounded-md border-b-0 bg-muted/50 px-3',
      )}
    >
      <div className="min-w-0">
        <div className={cn('text-sm', emphasis ? 'font-semibold' : 'font-medium')}>{label}</div>
        {why ? <div className="text-xs text-muted-foreground">{why}</div> : null}
      </div>
      <div
        className={cn(
          'shrink-0 whitespace-nowrap text-sm tabular-nums',
          emphasis ? 'font-semibold' : 'text-foreground',
        )}
      >
        {value}
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}

/** The plain-language headline sentence at the top of the popup. */
function summaryText(rec: ReorderRecommendation): string {
  const name = rec.product_name ? ` (${rec.product_name})` : '';
  if (rec.type === 'disposition') {
    if (rec.reason === 'dead') {
      return `${rec.sku}${name} hasn't moved within the dead-stock window, so it's tying up cash. Review it for disposal or a promotion.`;
    }
    const cover = rec.days_of_cover != null ? `${fmtInt(rec.days_of_cover)} days of cover` : 'more cover than the ceiling allows';
    return `${rec.sku}${name} has ${cover} — well above the healthy ceiling. Hold off reordering and consider a promotion or transfer.`;
  }
  if (rec.type === 'exception') {
    return `A reorder would fire for ${rec.sku}${name}, but no supplier is linked to source it. Link a supplier before this can be ordered.`;
  }
  // buy
  const qty = rec.order_qty != null ? fmtInt(rec.order_qty) : '';
  const net = dec(rec.net_position);
  if (rec.policy_type === 'min_max') {
    return `Order ${qty} units of ${rec.sku}${name}. Net position (${net}) has fallen to/below the minimum level (${dec(rec.min_qty)}), so it's time to replenish.`;
  }
  if (rec.policy_type === 'periodic_review') {
    return `Order ${qty} units of ${rec.sku}${name}. On the review cycle, net position (${net}) sits below the order-up-to target (${dec(rec.order_up_to)}), so it's time to replenish.`;
  }
  return `Order ${qty} units of ${rec.sku}${name}. Net position (${net}) has fallen to/below the reorder point (${dec(rec.reorder_point)}), so it's time to replenish.`;
}

function TypeChip({ rec }: { rec: ReorderRecommendation }) {
  if (rec.type === 'buy') {
    return (
      <Badge variant="info" appearance="light" size="md">
        <ShoppingCart className="size-3" /> Buy
      </Badge>
    );
  }
  if (rec.type === 'exception') {
    return (
      <Badge variant="warning" appearance="light" size="md">
        <AlertTriangle className="size-3" /> Exception
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" appearance="light" size="md">
      <Layers className="size-3" /> Disposition
    </Badge>
  );
}

/** Supplier block: chosen supplier + ranked alternatives (cost / lead / score). */
function SupplierBlock({ rec }: { rec: ReorderRecommendation }) {
  if (rec.is_exception || !rec.supplier) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-scm-stockout/40 bg-scm-stockout-soft p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-scm-stockout" aria-hidden />
        <span>
          No supplier is linked to this SKU, so the reorder can&apos;t be sourced. Link a supplier in
          the product record to turn this into a buy.
        </span>
      </div>
    );
  }
  const others = rec.alternatives.filter((a) => a.supplier_code !== rec.supplier?.supplier_code);
  const ranked: SupplierChoice[] = [rec.supplier, ...others];
  return (
    <div className="space-y-2">
      {rec.supplier_selection ? (
        <div className="text-xs text-muted-foreground">
          Chosen by {SELECTION_LABEL[rec.supplier_selection] ?? rec.supplier_selection}.
        </div>
      ) : null}
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 border-b bg-muted/40 px-3 py-1.5 text-2xs font-medium text-muted-foreground">
          <span>Supplier</span>
          <span className="text-right">Cost</span>
          <span className="text-right">Lead</span>
          <span className="text-right">Score</span>
        </div>
        {ranked.map((s) => {
          const selected = s.supplier_code === rec.supplier?.supplier_code;
          return (
            <div
              key={s.supplier_code}
              className={cn(
                'grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-3 px-3 py-1.5 text-sm',
                selected && 'bg-muted/40',
              )}
            >
              <span className="flex min-w-0 items-center gap-1">
                <span className="truncate" title={s.supplier_name ?? undefined}>
                  {s.supplier_name ?? EM_DASH}
                </span>
                {selected ? (
                  <Badge variant="primary" appearance="light" size="xs">
                    chosen
                  </Badge>
                ) : null}
              </span>
              <span className="text-right tabular-nums">{fmtMoney(s.unit_cost)}</span>
              <span className="text-right tabular-nums">
                {s.lead_time_days != null ? `${fmtInt(s.lead_time_days)}d` : EM_DASH}
              </span>
              <span className="text-right tabular-nums">
                {s.composite_score != null ? fmtInt(s.composite_score) : EM_DASH}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Forecast-demand derivation row — the daily usage that drives ROP and
 *  days-of-cover. Shared by the buy and disposition variants so the demand that
 *  PRODUCED the days-of-cover is always spelled out (value + /day + pattern). */
function ForecastDemandStep({ rec }: { rec: ReorderRecommendation }) {
  const pattern = xyzLabel(rec.xyz_class as XyzClass | null);
  return (
    <Step
      label="Forecast demand"
      value={`${dec(rec.forecast_daily_demand)} /day`}
      why={
        <>
          Average daily usage over recent sales history. Demand pattern:{' '}
          <span className="font-medium text-foreground">{pattern}</span>.
        </>
      }
    />
  );
}

/** Buy / exception derivation — the arithmetic laid out step by step. */
function BuyDerivation({ rec }: { rec: ReorderRecommendation }) {
  const ssWhy = rec.safety_stock_method
    ? SS_METHOD_WHY[rec.safety_stock_method]?.(rec)
    : undefined;
  const roundingNote: string[] = [];
  if (rec.moq != null && rec.moq > 0) roundingNote.push(`min order ${dec(rec.moq)}`);
  if (rec.order_multiple != null && rec.order_multiple > 0)
    roundingNote.push(`pack multiple ${dec(rec.order_multiple)}`);

  return (
    <div>
      <ForecastDemandStep rec={rec} />
      <Step
        label="Lead time"
        value={`${dec(rec.lead_time_days)} days`}
        why={
          rec.lead_time_source
            ? `Source: ${LEAD_SOURCE_WHY[rec.lead_time_source] ?? rec.lead_time_source}.`
            : undefined
        }
      />
      <Step
        label="Safety stock"
        value={`${dec(rec.safety_stock)} units`}
        why={
          <>
            {ssWhy ? `Method: ${ssWhy}.` : null}
            {rec.safety_stock_fallback ? (
              <span className="mt-0.5 block text-amber-600">{rec.safety_stock_fallback}</span>
            ) : null}
          </>
        }
      />
      <Step
        emphasis
        label="Reorder point"
        why="Demand × lead time + safety stock"
        value={
          <>
            {dec(rec.forecast_daily_demand)} × {dec(rec.lead_time_days)} +{' '}
            {dec(rec.safety_stock)} = <span className="text-foreground">{dec(rec.reorder_point)}</span>
          </>
        }
      />
      <Step
        label="Net position"
        value={dec(rec.net_position)}
        why="On hand + on order − committed"
      />
      <Step
        label="Days of cover"
        value={rec.days_of_cover != null ? `${fmtInt(rec.days_of_cover)} days` : EM_DASH}
        why="How long the net position lasts at the forecast demand"
      />
      <Step
        emphasis
        label="Order-up-to target"
        why={`Reorder point + one review period (${dec(rec.review_days)} days) of demand`}
        value={
          <>
            {dec(rec.reorder_point)} + {dec(rec.forecast_daily_demand)} × {dec(rec.review_days)} ={' '}
            <span className="text-foreground">{dec(rec.order_up_to)}</span>
          </>
        }
      />
      {rec.type === 'buy' ? (
        <Step
          emphasis
          label="Order quantity"
          why={
            roundingNote.length
              ? `Order-up-to − net, rounded to ${roundingNote.join(' / ')}`
              : 'Order-up-to − net position'
          }
          value={
            <>
              {dec(rec.order_up_to)} − {dec(rec.net_position)}
              {rec.recommended_qty != null ? <> = {dec(rec.recommended_qty)}</> : null}
              {' → '}
              <span className="text-foreground">{fmtInt(rec.order_qty)}</span>
            </>
          }
        />
      ) : (
        <Step
          label="Order quantity"
          value={EM_DASH}
          why="Can't be sized until a supplier (with min-order / pack rules) is linked."
        />
      )}
    </div>
  );
}

/** Disposition explanation — why (dead / overstock) + suggested action. No buy maths. */
function DispositionExplanation({ rec }: { rec: ReorderRecommendation }) {
  const isDead = rec.reason === 'dead';
  return (
    <div>
      <Step
        label={isDead ? 'Dead stock' : 'Overstock'}
        value={
          <Badge variant="secondary" appearance="light" size="md">
            {isDead ? <Ban className="size-3" /> : <PackageX className="size-3" />}
            {isDead ? 'No recent movement' : 'Excess cover'}
          </Badge>
        }
        why={
          isDead
            ? 'No consumption recorded within the dead-stock window.'
            : `Days of cover exceeds the ${REASON_NOUN.overstock}.`
        }
      />
      {/* Surface the demand that PRODUCED the days-of-cover so the "why" is
          traceable, not just asserted (mirrors the buy variant's row). */}
      <ForecastDemandStep rec={rec} />
      {rec.days_of_cover != null ? (
        <Step
          emphasis
          label="Days of cover"
          why="Net position ÷ forecast demand"
          value={
            <>
              {dec(rec.net_position)} ÷ {dec(rec.forecast_daily_demand)} /day ={' '}
              <span className="text-foreground">{fmtInt(rec.days_of_cover)} days</span>
            </>
          }
        />
      ) : null}
      <Step label="Net position" value={dec(rec.net_position)} why="On hand + on order − committed" />
      <Step
        label="Suggested action"
        value={
          <span className="font-medium">
            {rec.disposition_action === 'discontinue'
              ? 'Discontinue'
              : rec.disposition_action === 'promo'
                ? 'Promote'
                : 'Hold'}
          </span>
        }
        why={rec.reason_label ?? undefined}
      />
      {rec.transfer_flag ? (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-scm-incoming/40 bg-scm-incoming-soft p-3 text-sm">
          <ArrowRightLeft className="mt-0.5 size-4 shrink-0 text-scm-incoming" aria-hidden />
          <span>{rec.transfer_flag}</span>
        </div>
      ) : null}
    </div>
  );
}

export function ReorderExplanationDialog({
  rec,
  open,
  onOpenChange,
  recs,
  totalCount,
  pageItemOffset,
  onNavigate,
}: {
  rec: ReorderRecommendation | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current grid-page rows, in the active sort/filter order — powers the
   *  in-place prev/next pager so the user can step recommendations without
   *  closing the popup. Optional so the dialog still renders standalone. */
  recs?: ReorderRecommendation[];
  /** Full filtered total (all pages) — the pager's denominator. */
  totalCount?: number;
  /** 0-based index of the first `recs` row within the full filtered list. */
  pageItemOffset?: number;
  /** Step to a neighbouring recommendation in place (no close). */
  onNavigate?: (rec: ReorderRecommendation) => void;
}) {
  const isBuyLike = rec?.type === 'buy' || rec?.type === 'exception';
  const canPage = !!recs && recs.length > 1 && !!rec && !!onNavigate;

  // Arrow-key stepping between recommendations while the popup is open. Safe to
  // bind on the content: the dialog has no text inputs to hijack.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!canPage || !recs || !rec || !onNavigate) return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const idx = recs.findIndex((r) => r.id === rec.id);
      if (idx < 0) return;
      const nextIdx = e.key === 'ArrowRight' ? idx + 1 : idx - 1;
      if (nextIdx < 0 || nextIdx >= recs.length) return;
      e.preventDefault();
      onNavigate(recs[nextIdx]);
    },
    [canPage, recs, rec, onNavigate],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal>
      {/* `overflow-y-hidden` overrides the base `overflow-y-auto` (same
          tailwind-merge group) so only the body scrolls — the header + pager
          stay pinned. `max-h-[85dvh]` keeps the tallest derivation on-screen,
          reachable at ~375px mobile width. */}
      <DialogContent
        className="max-h-[85dvh] max-w-xl overflow-y-hidden sm:max-w-2xl"
        onKeyDown={handleKeyDown}
      >
        <DialogHeader className="shrink-0">
          <div className="flex items-start justify-between gap-3 pe-8">
            <DialogTitle>How this recommendation was reached</DialogTitle>
            {canPage ? (
              <RecordNavigation
                basePath=""
                currentId={rec!.id}
                items={recs!}
                totalCount={totalCount}
                pageItemOffset={pageItemOffset ?? 0}
                circular={false}
                ariaLabel="recommendation"
                className="shrink-0"
                onSelect={(id) => {
                  const next = recs!.find((r) => r.id === id);
                  if (next) onNavigate!(next);
                }}
              />
            ) : null}
          </div>
          <DialogDescription>
            {rec ? (
              <span className="flex flex-wrap items-center gap-2">
                <TypeChip rec={rec} />
                <span className="font-medium text-foreground">{rec.sku}</span>
                {rec.product_name ? <span>— {rec.product_name}</span> : null}
              </span>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {rec ? (
          // `key` resets scroll to top when stepping to a neighbouring rec.
          <DialogBody key={rec.id} className="grow space-y-5 overflow-y-auto min-h-0 -mx-6 px-6">
            {/* Plain-language headline */}
            <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
              {summaryText(rec)}
            </div>

            {/* Step-by-step derivation */}
            <div>
              <SectionTitle>{isBuyLike ? 'How the numbers were reached' : "Why it's flagged"}</SectionTitle>
              {isBuyLike ? <BuyDerivation rec={rec} /> : <DispositionExplanation rec={rec} />}
            </div>

            {/* Policy + trigger */}
            <div>
              <SectionTitle>Policy &amp; trigger</SectionTitle>
              <Step
                label="Policy applied"
                value={
                  rec.policy_type ? (POLICY_TYPE_LABEL[rec.policy_type] ?? rec.policy_type) : EM_DASH
                }
                why={rec.is_network ? 'Planned across the network (aggregated).' : undefined}
              />
              <Step
                label="Trigger"
                value={<span className="text-end">{rec.reason_label ?? EM_DASH}</span>}
              />
            </div>

            {/* Confidence */}
            <div>
              <SectionTitle>Confidence</SectionTitle>
              <div className="flex flex-wrap items-center gap-2">
                {rec.confidence ? (
                  <ConfidenceBadge confidence={rec.confidence} sampleSize={rec.sample_size} />
                ) : (
                  <span className="text-sm text-muted-foreground">{EM_DASH}</span>
                )}
                <span className="text-xs text-muted-foreground">
                  Reflects data sufficiency (demand pattern{' '}
                  <span className="font-medium">{xyzLabel(rec.xyz_class as XyzClass | null)}</span> ·{' '}
                  {fmtInt(rec.sample_size)} sample), not that the number is guaranteed correct.
                </span>
              </div>
            </div>

            {/* Supplier (buy / exception) */}
            {isBuyLike ? (
              <div>
                <SectionTitle>Supplier</SectionTitle>
                <SupplierBlock rec={rec} />
              </div>
            ) : null}

            {/* Network allocation */}
            {rec.is_network && rec.allocation && rec.allocation.length ? (
              <div>
                <SectionTitle>Per-warehouse allocation</SectionTitle>
                <div className="overflow-hidden rounded-lg border border-border">
                  {rec.allocation.map((a) => (
                    <div
                      key={a.warehouse_code}
                      className="flex items-center justify-between border-b px-3 py-1.5 text-sm last:border-b-0"
                    >
                      <span className="truncate" title={a.warehouse_name}>
                        <span className="font-medium">{a.warehouse_code}</span>{' '}
                        <span className="text-xs text-muted-foreground">{a.warehouse_name}</span>
                      </span>
                      <span className="tabular-nums">{fmtInt(a.qty)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </DialogBody>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
