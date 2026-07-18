'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { Popover as PopoverPrimitive } from 'radix-ui';
import {
  AlertTriangle,
  ArrowRightLeft,
  Ban,
  ChevronDown,
  ExternalLink,
  Layers,
  PackageX,
  SendHorizontal,
  ShoppingCart,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import RecordNavigation from '@/components/common/RecordNavigation';
import { cn } from '@/lib/utils';
import {
  useAskRecommendation,
  useRecommendationAdvisory,
  useRecommendationExplanation,
} from '../hooks/useExplainer';
import { REFUSAL } from '../lib/explainerMockStore';
import type { AskTurn } from '../types/explainer.types';
import { xyzLabel } from '../../lib/health';
import type { XyzClass } from '../../types/scm.types';
import { EM_DASH, fmtInt, fmtMoney, fmtPct } from '../../lib/format';
import { ConfidenceBadge } from '../../components/HealthIndicators';
import type {
  RankFactor,
  ReorderRecommendation,
  SupplierChoice,
} from '../types/reorder.types';

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

const RANK_FACTOR_LABEL: Record<RankFactor['key'], string> = {
  urgency: 'Urgency',
  margin: 'Margin',
  abc: 'Value',
  priority: 'SO priority',
  committed: 'Committed vs forecast',
  market: 'Market trend',
};

/** M4 "why this rank" block — which cash-ranking factors were present, and which
 *  dominated. Margin is DROPPED (not zeroed) for uncosted SKUs (M4-D14), shown
 *  greyed so a novice sees exactly why urgency ended up dominant. */
function RankExplanation({ rec }: { rec: ReorderRecommendation }) {
  const factors = rec.rank_factors ?? [];
  const present = factors.filter((f) => f.present && f.value !== null);
  const dominant = present.reduce<RankFactor | null>(
    (top, f) => (top === null || f.weight * (f.value ?? 0) > top.weight * (top.value ?? 0) ? f : top),
    null,
  );
  const isNeedsCost = rec.funding_status === 'needs_cost';
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {isNeedsCost ? (
          <Badge variant="secondary" appearance="light" size="md">
            No supplier cost
          </Badge>
        ) : (
          <Badge variant="primary" appearance="light" size="md">
            Rank {rec.rank}
          </Badge>
        )}
        <span className="text-muted-foreground">
          {isNeedsCost
            ? "Can't be cash-ranked or funded until a supplier cost is added."
            : `Score ${rec.rank_score != null ? rec.rank_score.toFixed(2) : EM_DASH} · cash impact ${
                rec.cash_impact != null ? fmtMoney(rec.cash_impact) : 'unknown (uncosted)'
              }`}
        </span>
      </div>
      <div className="overflow-hidden rounded-lg border border-border">
        {factors.map((f) => {
          const isDominant = dominant?.key === f.key;
          return (
            <div
              key={f.key}
              className={cn(
                'flex items-center justify-between gap-3 border-b px-3 py-1.5 text-sm last:border-b-0',
                !f.present && 'opacity-55',
              )}
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="truncate">{RANK_FACTOR_LABEL[f.key]}</span>
                {isDominant ? (
                  <Badge variant="primary" appearance="light" size="xs">
                    top driver
                  </Badge>
                ) : null}
              </span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {f.present && f.value !== null ? (
                  <>
                    {fmtPct(f.value)} <span className="text-2xs">· weight {f.weight}</span>
                  </>
                ) : (
                  <span className="text-2xs italic">dropped — no cost on file</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {rec.market_signal ? (
        <div className="flex items-start gap-2 rounded-lg border border-scm-incoming/40 bg-scm-incoming-soft p-2.5 text-xs">
          <TrendingUp className="mt-0.5 size-3.5 shrink-0 text-scm-incoming" aria-hidden />
          <span>
            <span className="font-medium">Market trend applied:</span> {rec.market_signal} — this
            lifted the funding priority (rank), not the order quantity.
          </span>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {isNeedsCost
          ? 'Without a supplier cost the margin factor drops out and there is no cash impact to weigh against the budget, so this buy stays in Needs cost. It is still a real must-buy — add a cost to fund it.'
          : 'Rank orders the buys for funding: higher-ranked buys are funded first when the budget is tight. Factors without data are dropped so they never dilute the score.'}
      </p>
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

const CONFIDENCE_LABEL: Record<string, string> = { high: 'High', medium: 'Medium', low: 'Low' };

/** One label/value line inside the supplier score popover. */
function DetailLine({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-3 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end">
        <span className="font-medium tabular-nums">{value}</span>
        {sub ? <span className="ms-1 text-2xs text-muted-foreground">{sub}</span> : null}
      </span>
    </div>
  );
}

/** Click-to-reveal supplier scorecard — kept OUT of the always-on table so the row
 *  stays scannable; a planner who wants "why this supplier" clicks the chevron and
 *  gets the composite score breakdown, reliability, cost + ordering constraints,
 *  plus how it ranked vs the chosen supplier. Frozen numbers only (M5 boundary). */
function SupplierScoreDetail({
  s,
  selected,
  chosen,
}: {
  s: SupplierChoice;
  selected: boolean;
  chosen: SupplierChoice | null;
}) {
  const costDelta =
    !selected && chosen?.unit_cost != null && s.unit_cost != null
      ? s.unit_cost - chosen.unit_cost
      : null;
  const leadDelta =
    !selected && chosen?.lead_time_days != null && s.lead_time_days != null
      ? s.lead_time_days - chosen.lead_time_days
      : null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-0.5 rounded-sm px-1 text-2xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          title="Supplier score detail"
          aria-label={`Score detail for ${s.supplier_name ?? s.supplier_code}`}
        >
          Details
          <ChevronDown className="size-3" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPrimitive.Portal>
        <PopoverContent align="end" collisionPadding={8} className="w-72 p-0">
          <div className="flex items-center gap-2 border-b px-3 py-2 text-xs font-medium">
            <span className="truncate">{s.supplier_name ?? s.supplier_code}</span>
            <Badge variant={selected ? 'primary' : 'secondary'} appearance="light" size="xs">
              {selected ? 'chosen' : 'alternative'}
            </Badge>
            {s.is_primary ? (
              <Badge variant="secondary" appearance="light" size="xs">
                primary
              </Badge>
            ) : null}
          </div>
          <div className="divide-y">
            <DetailLine
              label="Performance score"
              value={s.composite_score != null ? fmtInt(s.composite_score) : EM_DASH}
              sub={
                s.confidence
                  ? `${CONFIDENCE_LABEL[s.confidence] ?? s.confidence} · ${fmtInt(s.sample_size ?? 0)} obs`
                  : s.sample_size != null
                    ? `${fmtInt(s.sample_size)} obs`
                    : undefined
              }
            />
            <DetailLine
              label="Lead time"
              value={s.lead_time_days != null ? `${fmtInt(s.lead_time_days)}d` : EM_DASH}
              sub={
                [
                  s.lead_time_source ? LEAD_SOURCE_WHY[s.lead_time_source] ?? s.lead_time_source : null,
                  s.lead_time_variance != null ? `±${dec(Math.sqrt(Math.max(s.lead_time_variance, 0)))}d` : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || undefined
              }
            />
            <DetailLine label="Unit cost" value={fmtMoney(s.unit_cost)} />
            {s.moq != null && s.moq > 0 ? (
              <DetailLine label="Min order" value={fmtInt(s.moq)} />
            ) : null}
            {s.order_multiple != null && s.order_multiple > 0 ? (
              <DetailLine label="Pack multiple" value={fmtInt(s.order_multiple)} />
            ) : null}
            {!selected && (costDelta != null || leadDelta != null) ? (
              <div className="px-3 py-1.5 text-2xs text-muted-foreground">
                vs chosen:{' '}
                {costDelta != null ? (
                  <span className={cn(costDelta > 0 ? 'text-scm-stockout' : 'text-scm-incoming')}>
                    {costDelta > 0 ? '+' : ''}
                    {fmtMoney(costDelta)}
                  </span>
                ) : null}
                {costDelta != null && leadDelta != null ? ', ' : ''}
                {leadDelta != null ? (
                  <span className={cn(leadDelta > 0 ? 'text-scm-stockout' : 'text-scm-incoming')}>
                    {leadDelta > 0 ? '+' : ''}
                    {fmtInt(leadDelta)}d lead
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        </PopoverContent>
      </PopoverPrimitive.Portal>
    </Popover>
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
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-3 border-b bg-muted/40 px-3 py-1.5 text-2xs font-medium text-muted-foreground">
          <span>Supplier</span>
          <span className="text-right">Cost</span>
          <span className="text-right">Lead</span>
          <span className="text-right">Score</span>
          <span className="text-right sr-only">Detail</span>
        </div>
        {ranked.map((s) => {
          const selected = s.supplier_code === rec.supplier?.supplier_code;
          return (
            <div
              key={s.supplier_code}
              className={cn(
                'grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-x-3 px-3 py-1.5 text-sm',
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
              <span className="text-right">
                <SupplierScoreDetail s={s} selected={selected} chosen={rec.supplier} />
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
        label="Runway"
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
            : `Runway exceeds the ${REASON_NOUN.overstock}.`
        }
      />
      {/* Surface the demand that PRODUCED the days-of-cover so the "why" is
          traceable, not just asserted (mirrors the buy variant's row). */}
      <ForecastDemandStep rec={rec} />
      {rec.days_of_cover != null ? (
        <Step
          emphasis
          label="Runway"
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

/**
 * M5 semantic layer — the LLM narrator that sits ON TOP of the deterministic
 * derivation above. A generated one-sentence explanation (clearly badged "AI" so
 * it's never mistaken for the frozen arithmetic below it) plus an optional market
 * advisory. Buy / exception recs only — disposition rows don't get a buy
 * narrative. Speaks only the rec's frozen numbers (M5 boundary).
 */
function AiSummaryBlock({ rec, enabled }: { rec: ReorderRecommendation; enabled: boolean }) {
  const explanation = useRecommendationExplanation(rec, enabled);
  const advisory = useRecommendationAdvisory(rec, enabled);

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-primary/25 bg-primary/5 p-3">
        <div className="mb-1.5 flex items-center gap-1.5">
          <Sparkles className="size-3.5 text-primary" aria-hidden />
          <span className="text-2xs font-semibold uppercase tracking-wide text-primary">
            AI summary
          </span>
        </div>
        {explanation.isLoading ? (
          <div className="space-y-1.5" aria-label="Generating explanation">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-4/5" />
          </div>
        ) : explanation.isError ? (
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t generate a plain-language summary — the derivation below still applies.
          </p>
        ) : (
          <p className="text-sm">{explanation.data?.explanation}</p>
        )}
      </div>

      {/* Market advisory — subtle info callout, only when a signal matched. */}
      {advisory.data?.advisory ? (
        <div className="flex items-start gap-2 rounded-lg border border-scm-incoming/40 bg-scm-incoming-soft p-3 text-sm">
          <TrendingUp className="mt-0.5 size-4 shrink-0 text-scm-incoming" aria-hidden />
          <div className="min-w-0 space-y-1">
            <Badge variant="info" appearance="light" size="xs">
              Market signal
            </Badge>
            <p>{advisory.data.advisory}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * M5 Ask box — a bounded Q&A grounded in THIS rec's frozen numbers. Keeps a short
 * transcript in local state (reset when the dialog steps to another rec via the
 * `key` on DialogBody). A question that needs a number the rec doesn't carry
 * comes back as the exact refusal string, which we style as a muted turn so the
 * user sees the model declining rather than guessing.
 */
function AskSection({ rec }: { rec: ReorderRecommendation }) {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const ask = useAskRecommendation(rec);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || ask.isPending) return;
    setQuestion('');
    try {
      const res = await ask.mutateAsync(q);
      setTurns((prev) => [...prev, { question: q, answer: res.answer, refused: res.answer === REFUSAL }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to answer question';
      setTurns((prev) => [...prev, { question: q, answer: msg, refused: true }]);
    }
  };

  return (
    <div>
      <SectionTitle>Ask about this recommendation</SectionTitle>
      {turns.length ? (
        <div className="mb-3 space-y-3">
          {turns.map((t, i) => (
            <div key={i} className="space-y-1">
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-lg bg-primary/10 px-3 py-1.5 text-sm">
                  {t.question}
                </div>
              </div>
              <div className="flex justify-start">
                <div
                  className={cn(
                    'flex max-w-[85%] items-start gap-1.5 rounded-lg px-3 py-1.5 text-sm',
                    t.refused ? 'bg-muted text-muted-foreground italic' : 'bg-muted',
                  )}
                >
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
                  <span>{t.answer}</span>
                </div>
              </div>
            </div>
          ))}
          {ask.isPending ? (
            <div className="flex justify-start">
              <div className="flex max-w-[85%] items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5">
                <Skeleton className="h-3.5 w-32" />
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <form onSubmit={submit} className="flex items-center gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What lead time was used?"
          aria-label="Ask about this recommendation"
        />
        <Button type="submit" disabled={!question.trim() || ask.isPending}>
          <SendHorizontal className="size-4" aria-hidden />
          Ask
        </Button>
      </form>
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
  poLink,
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
  /** The draft PO this rec was confirmed into (M8-F8) — drives the "View PO"
   *  button that deep-links to the PO detail page. null when not yet confirmed. */
  poLink?: { po_number: string; po_id: string | null } | null;
}) {
  const isBuyLike = rec?.type === 'buy' || rec?.type === 'exception';
  const canPage = !!recs && recs.length > 1 && !!rec && !!onNavigate;

  // Arrow-key stepping between recommendations while the popup is open. Ignore
  // arrows fired from a text field (the M5 Ask input lives in this DialogContent),
  // so moving the caret mid-question never jumps to another recommendation.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!canPage || !recs || !rec || !onNavigate) return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      )
        return;
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
                {/* View PO (M8-F8): once the line is confirmed into a draft PO, jump
                    straight to that PO's detail page. */}
                {poLink?.po_id ? (
                  <Button asChild variant="outline" size="sm" className="ms-auto h-7 shrink-0 px-2 text-xs">
                    <Link href={`/scm/purchase-orders/${poLink.po_id}`} title={`View ${poLink.po_number}`}>
                      <ExternalLink className="size-3.5" aria-hidden />
                      View PO
                    </Link>
                  </Button>
                ) : null}
              </span>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {rec ? (
          // `key` resets scroll to top when stepping to a neighbouring rec.
          <DialogBody key={rec.id} className="grow space-y-5 overflow-y-auto min-h-0 -mx-6 px-6">
            {/* M5 AI narration + market advisory IS the headline for EVERY rec type
                (buy / exception / disposition) — the old deterministic one-liner was
                redundant with it. */}
            <AiSummaryBlock rec={rec} enabled={open} />

            {/* Step-by-step derivation */}
            <div>
              <SectionTitle>{isBuyLike ? 'How the numbers were reached' : "Why it's flagged"}</SectionTitle>
              {isBuyLike ? <BuyDerivation rec={rec} /> : <DispositionExplanation rec={rec} />}
            </div>

            {/* Cash ranking (M4 buy recs only) */}
            {rec.type === 'buy' && rec.rank != null ? (
              <div>
                <SectionTitle>
                  {rec.funding_status === 'needs_cost' ? 'Why it needs a cost' : 'Why this rank'}
                </SectionTitle>
                <RankExplanation rec={rec} />
              </div>
            ) : null}

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

            {/* M5 Ask box — bounded Q&A over this rec's frozen numbers (buy /
                exception only). Lives at the bottom so the derivation is read
                first; the dialog body is already mobile-scrollable. */}
            <AskSection rec={rec} />
          </DialogBody>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
