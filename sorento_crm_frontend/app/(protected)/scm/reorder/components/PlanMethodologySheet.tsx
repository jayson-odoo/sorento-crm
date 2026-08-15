'use client';

import type { ReactNode } from 'react';
import {
  CalendarClock,
  Coins,
  Gauge,
  Info,
  ListOrdered,
  Boxes,
  PackageSearch,
  Ruler,
  Warehouse,
} from 'lucide-react';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';

/**
 * SCM M8-F15 - "How this plan was built" methodology explainer.
 *
 * An (i) beside the "Today's plan" header opens this right-side slide-over. It
 * walks the DETERMINISTIC engine that produces the daily plan, step by step, in
 * plain language so the user trusts the unattended recommendations.
 *
 * GUARDRAIL: every number below is an AUTHORED constant that mirrors the engine's
 * locked defaults (reorder_engine.py / cash_ranking.py / analytics_service.py) - it
 * is NOT sourced from an LLM. The run-context strip is likewise built from the
 * run detail the page already loads, never from the LLM run-overview prose, so no
 * LLM-generated figure is ever surfaced as fact. Per-SKU policies can override the
 * defaults; these are the starting values the plan uses.
 */

/** Ranking factors + their real default weights (cash_ranking.DEFAULT_WEIGHTS).
 *  "abc" is shown as the layman term "Value" (M8-F4). */
const RANK_FACTORS: { label: string; weight: number; note: string }[] = [
  { label: 'Urgency', weight: 40, note: 'how close to running out' },
  { label: 'Margin', weight: 30, note: 'profit per unit sold' },
  { label: 'Value', weight: 15, note: 'A / B / C importance of the product' },
  { label: 'Committed vs forecast', weight: 5, note: 'orders already promised vs expected demand' },
  { label: 'Market', weight: 10, note: 'only when a market signal is included via the assistant' },
];

/** A single top buy from THIS run, reduced to the numbers the methodology steps
 *  cite. All values are the engine's FROZEN figures off the plan rows - no LLM. */
export interface PlanMethodologyBuy {
  sku: string;
  demand: number | null; // avg daily demand (forecast_daily_demand)
  net: number | null;
  safetyStock: number | null;
  leadTime: number | null;
  reorderPoint: number | null;
  orderUpTo: number | null;
  orderQty: number;
  daysCover: number | null;
}

export interface PlanMethodologyFacts {
  topBuys: PlanMethodologyBuy[];
  withinCount: number;
  overCount: number;
  committed: number;
  free: number;
  budget: number;
}

/** Which per-run numbers a step reveals when the user expands "See this run's numbers". */
type StepDetail = 'demand' | 'net' | 'rop' | 'orderqty' | 'funding';

interface MethodStep {
  icon: ReactNode;
  title: string;
  blurb: string;
  formula?: string;
  factors?: boolean;
  detail?: StepDetail;
}

const STEPS: MethodStep[] = [
  {
    icon: <Gauge className="size-4" aria-hidden />,
    title: 'Measure demand',
    blurb:
      'We measure how fast each product actually sells, from real delivery-order outflow over the last 90 days.',
    formula:
      'Avg daily demand = 90-day delivery-order outflow / 90 days, plus a coefficient of variation (how steady or spiky that demand is).',
    detail: 'demand',
  },
  {
    icon: <Boxes className="size-4" aria-hidden />,
    title: 'Current position',
    blurb: 'What you can genuinely sell right now, after accounting for stock already spoken for.',
    formula: 'Net available = on hand + on order - committed (open sales orders).',
    detail: 'net',
  },
  {
    icon: <Ruler className="size-4" aria-hidden />,
    title: 'When to reorder',
    blurb:
      'The stock level that should trigger a fresh order, with a buffer for demand that swings and suppliers that run late.',
    formula:
      'Reorder point = safety stock + (demand rate x lead time). Safety stock defaults to 7 days of demand; lead time is the days from raising a PO to receiving goods (default 30).',
    detail: 'rop',
  },
  {
    icon: <PackageSearch className="size-4" aria-hidden />,
    title: 'How much to order',
    blurb: 'Enough to cover until the next review, then rounded to what the supplier will actually accept.',
    formula:
      'Order-up-to = reorder point + (demand rate x review period, default 30 days). Order qty = order-up-to - net available, rounded up to the supplier minimum order quantity and order multiple.',
    detail: 'orderqty',
  },
  {
    icon: <ListOrdered className="size-4" aria-hidden />,
    title: 'Priority',
    blurb:
      'Each buy is scored so the most important ones rise to the top when cash is tight. Any factor with no data is dropped, never counted as zero.',
    factors: true,
  },
  {
    icon: <Coins className="size-4" aria-hidden />,
    title: 'Cash funding',
    blurb:
      'The plan funds the highest-priority buys first until the budget is spent; a buy is funded only if its full cost fits the money left, otherwise it defers.',
    formula:
      'The daily plan starts with a full budget (everything funded). Tighten the budget on the page to push lower-priority buys into Over budget.',
    detail: 'funding',
  },
  {
    icon: <Boxes className="size-4" aria-hidden />,
    title: 'Stock allocation and market context',
    blurb:
      'Products sitting idle too long (dead stock) or holding far more cover than needed (overstock) are flagged to hold, promote, or discontinue. Live market trends never change a quantity on their own - they only enter the plan when you accept a suggestion in the assistant chat.',
  },
];

export interface PlanMethodologyRunContext {
  dateLabel?: string;
  timeLabel?: string;
  warehouseCount?: number;
  warehouseCodes?: string[];
  isPastRun?: boolean;
}

/** Human label for the warehouses a run covered, degrading gracefully. */
function warehouseLabel(ctx?: PlanMethodologyRunContext | null): string {
  if (!ctx) return 'All warehouses';
  const codes = ctx.warehouseCodes ?? [];
  const count = ctx.warehouseCount ?? codes.length;
  if (count === 0) return 'All warehouses';
  if (count === 1) return codes[0] ?? '1 warehouse';
  if (codes.length > 0 && codes.length <= 3) return codes.join(', ');
  return `${count} warehouses`;
}

const nf = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
const money = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
/** Format a nullable number, dash when the engine had no value for it. */
function n(v: number | null | undefined, whole = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-';
  return (whole ? nf0 : nf).format(v);
}

/** Compact per-run numbers table revealed under a step. Columns depend on the step,
 *  so each step shows exactly the figures it just described - grounded in THIS run's
 *  frozen values, never an LLM number. Collapsed by default (discover on demand). */
function StepNumbers({ kind, facts }: { kind: StepDetail; facts?: PlanMethodologyFacts | null }) {
  if (!facts) return null;
  if (kind === 'funding') {
    const rows: [string, string][] = [
      ['Within budget', `${n(facts.withinCount, true)} buys`],
      ['Over budget', `${n(facts.overCount, true)} buys`],
      ['Cash budget', `RM ${money.format(facts.budget)}`],
      ['Committed', `RM ${money.format(facts.committed)}`],
      ['Free', `RM ${money.format(facts.free)}`],
    ];
    return (
      <details className="group mt-3">
        <summary className="cursor-pointer list-none text-xs font-medium text-primary underline-offset-2 hover:underline">
          See this run&apos;s numbers
        </summary>
        <div className="mt-2 grid grid-cols-1 gap-1.5 rounded-lg border bg-muted/30 p-3 sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-3 text-xs">
              <span className="text-muted-foreground">{k}</span>
              <span className="font-medium tabular-nums text-foreground">{v}</span>
            </div>
          ))}
        </div>
      </details>
    );
  }

  const buys = facts.topBuys.slice(0, 4);
  if (buys.length === 0) return null;
  const cols: { head: string; cell: (b: PlanMethodologyBuy) => string }[] =
    kind === 'demand'
      ? [{ head: 'Avg daily demand', cell: (b) => n(b.demand) }]
      : kind === 'net'
        ? [{ head: 'Net available', cell: (b) => n(b.net) }]
        : kind === 'rop'
          ? [
              { head: 'Safety stock', cell: (b) => n(b.safetyStock, true) },
              { head: 'Lead time', cell: (b) => (b.leadTime == null ? '-' : `${n(b.leadTime, true)}d`) },
              { head: 'Reorder point', cell: (b) => n(b.reorderPoint, true) },
            ]
          : [
              { head: 'Order-up-to', cell: (b) => n(b.orderUpTo, true) },
              { head: 'Net', cell: (b) => n(b.net, true) },
              { head: 'Order qty', cell: (b) => n(b.orderQty, true) },
            ];

  return (
    <details className="group mt-3">
      <summary className="cursor-pointer list-none text-xs font-medium text-primary underline-offset-2 hover:underline">
        See this run&apos;s numbers
      </summary>
      <div className="mt-2 overflow-x-auto rounded-lg border bg-muted/30">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="px-3 py-1.5 text-left font-medium">SKU</th>
              {cols.map((c) => (
                <th key={c.head} className="px-3 py-1.5 text-right font-medium">
                  {c.head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {buys.map((b) => (
              <tr key={b.sku} className="border-b last:border-0">
                <td className="px-3 py-1.5 font-medium text-foreground">{b.sku}</td>
                {cols.map((c) => (
                  <td key={c.head} className="px-3 py-1.5 text-right tabular-nums text-foreground">
                    {c.cell(b)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-2xs text-muted-foreground">Top buys by priority in this run.</p>
    </details>
  );
}

/** Small key-value row in the run-context strip. */
function ContextRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 text-muted-foreground" aria-hidden>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="truncate text-sm font-medium text-foreground" title={value}>
          {value}
        </div>
      </div>
    </div>
  );
}

export function PlanMethodologySheet({
  runContext,
  facts,
  trigger,
}: {
  runContext?: PlanMethodologyRunContext | null;
  /** THIS run's frozen numbers, so each step can reveal the actual figures it
   *  describes (M8: discoverable, not all shown at once). */
  facts?: PlanMethodologyFacts | null;
  trigger?: ReactNode;
}) {
  const generatedAt =
    runContext?.dateLabel && runContext?.timeLabel
      ? `${runContext.dateLabel}, ${runContext.timeLabel}`
      : runContext?.dateLabel || 'Latest available snapshot';

  return (
    <Sheet>
      <SheetTrigger asChild>
        {trigger ?? (
          <button
            type="button"
            aria-label="How this plan was built"
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Info className="size-4" aria-hidden />
          </button>
        )}
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-xl"
      >
        <SheetHeader className="border-b bg-muted/30 px-6 py-5 text-start">
          <SheetTitle className="text-lg">How this plan was built</SheetTitle>
          <SheetDescription>
            The daily plan is produced by a fixed, repeatable calculation - no guesswork. Here is
            each step, in order.
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="space-y-6 px-6 py-5">
          {/* This run - context strip (deterministic, from the loaded run detail) */}
          <section
            aria-label="This run"
            className="rounded-xl border bg-card p-4"
            data-testid="plan-methodology-run-context"
          >
            <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              This run
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <ContextRow
                icon={<CalendarClock className="size-4" aria-hidden />}
                label="Generated"
                value={generatedAt}
              />
              <ContextRow
                icon={<Warehouse className="size-4" aria-hidden />}
                label="Coverage"
                value={warehouseLabel(runContext)}
              />
              <ContextRow
                icon={<Coins className="size-4" aria-hidden />}
                label="Budget"
                value={runContext?.isPastRun ? 'As run' : 'Full budget - tighten to defer'}
              />
              <ContextRow
                icon={<Gauge className="size-4" aria-hidden />}
                label="Market insight"
                value="Off - only via the assistant"
              />
            </div>
          </section>

          {/* Method steps */}
          <ol className="space-y-4">
            {STEPS.map((step, i) => (
              <li
                key={step.title}
                className="rounded-xl border bg-card p-4"
                data-testid="plan-methodology-step"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                    {i + 1}
                  </span>
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <span className="text-primary">{step.icon}</span>
                    {step.title}
                  </div>
                </div>

                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{step.blurb}</p>

                {step.formula ? (
                  <p className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                    {step.formula}
                  </p>
                ) : null}

                {step.factors ? (
                  <ul className="mt-3 space-y-1.5">
                    {RANK_FACTORS.map((f) => (
                      <li key={f.label} className="flex items-center gap-2.5 text-xs">
                        <span className="inline-flex w-11 shrink-0 justify-center rounded-md bg-primary/10 py-0.5 font-semibold text-primary tabular-nums">
                          {f.weight}%
                        </span>
                        <span className="font-medium text-foreground">{f.label}</span>
                        <span className="truncate text-muted-foreground" title={f.note}>
                          {f.note}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}

                {step.detail ? <StepNumbers kind={step.detail} facts={facts} /> : null}
              </li>
            ))}
          </ol>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
