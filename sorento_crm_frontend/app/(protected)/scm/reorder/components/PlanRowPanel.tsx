'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import type { ApexOptions } from 'apexcharts';
import { TrendingDown } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { EM_DASH, fmtDecimal, fmtInt, fmtMoney, fmtSupplierCost } from '../../lib/format';
import { applySourceEdits, sourceEditsForTotal, type CoverProposal } from '../lib/coverPlan';
import { roundBuyQty } from '../lib/orderQtyLedger';
import { m8CashImpact } from '../lib/planRow';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import { suggestedDecisionFor, type PlanRowEdit } from '../lib/planEdits';
import {
  describeCheaper,
  describeLastPurchase,
  humanAge,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import {
  effectiveLevel,
  levelActionLabel,
  levelTerms,
  type LevelSuggestion,
} from '../lib/levelSuggestion';
import { healthVerdict, type ProductEconomics } from '../lib/productHealth';
import type { PoReceipt } from '../lib/poCover';
import type { PlanRowPriceMode } from '../types/decisions.types';

const ApexChart = dynamic(() => import('react-apexcharts').then((mod) => mod.default), {
  ssr: false,
});

/**
 * The whole decision for one product, in the row that asks it (plan 4.4).
 *
 * Four zones on one strip: how the shortage is covered, what it costs and from whom, the
 * AutoCount level and quantity to key back, and whether the product should still be sold.
 * They used to be five separate cells with five separate popovers, each writing to the
 * backend the moment it closed - so a buyer changing their mind produced four requests and
 * the row's own numbers moved under them mid-thought.
 *
 * NOTHING here writes. Every control calls `onEdit`, which lands in the page's draft map;
 * the pill turns Unsaved and Save persists the lot in one request. The per-location stock
 * table that used to live here moved into the On hand lightbox (R12) and SPO is stated as a
 * fact rather than offered as an input (R2) - it is already inside the net, so a "take SPO"
 * quantity would count it twice.
 */
export function PlanRowPanel({
  line,
  edit,
  decision,
  cover,
  poReceipts = [],
  price,
  cheaper = null,
  levelSuggestion,
  economics,
  healthWindows,
  staleAfterDays = 180,
  disabled = false,
  lockReason = null,
  onEdit,
  onUseSuggestion,
}: {
  line: PlanLine;
  /** The unsaved draft on this row, when there is one. */
  edit: PlanRowEdit | undefined;
  /** What is already persisted for it. */
  decision: PlanDecision | undefined;
  cover: CoverProposal;
  poReceipts?: PoReceipt[];
  price: PriceAdvice | undefined;
  cheaper?: CheaperAlternative | null;
  levelSuggestion: LevelSuggestion | undefined;
  economics: ProductEconomics | undefined;
  healthWindows?: { sold_window_months?: number; bought_window_months?: number };
  staleAfterDays?: number;
  /** A legacy run: the panel still renders, every input is dead (D8). */
  disabled?: boolean;
  lockReason?: string | null;
  onEdit: (patch: PlanRowEdit) => void;
  /** Drop this row's draft and go back to the engine's own mixture. */
  onUseSuggestion: () => void;
}) {
  const [chartOpen, setChartOpen] = useState(false);

  const suggested = suggestedDecisionFor(line, cover, poReceipts);
  // What the inputs READ: the draft first, then what is persisted, then the engine.
  const current: PlanDecision = edit?.decision ?? decision ?? suggested;
  const stockMax = cover.coverQty;
  const poMax = poReceipts.reduce((t, r) => t + r.remaining, 0);
  const needed = Math.ceil(line.order_qty);
  const skipped = Boolean(current.skip);

  const stockQty = current.stock?.qty ?? 0;
  const poQty = current.po ?? 0;
  const buyQty = current.buy ?? 0;
  const covered = stockQty + poQty + buyQty;
  const gap = covered - needed;

  const moq = line.order_qty_inputs.moq;
  const masterMoq = line.order_qty_inputs.master_moq;
  const moqValue = edit?.moq !== undefined ? edit.moq : moq;

  const priceMode: PlanRowPriceMode =
    edit?.priceMode ?? current.priceMode ?? decision?.priceMode ?? 'use_last';
  const supplierCode =
    edit?.supplierCode ?? current.supplierCode ?? line.supplier?.code ?? null;
  const picked = (line.alternatives ?? []).find((a) => a.value === supplierCode) ?? null;
  const hasPriceOnFile = Boolean(price?.last) || (line.unit_cost ?? 0) > 0;

  /** The unit the line is costed at: nothing while a new price is being asked for. */
  const unitCostBase =
    priceMode === 'ask_new'
      ? null
      : picked && picked.value !== line.supplier?.code
        ? picked.unit_cost_base
        : line.unit_cost_base;
  const lineCost =
    unitCostBase === null || unitCostBase === undefined
      ? null
      : m8CashImpact({ order_qty: buyQty, unit_cost: line.unit_cost, unit_cost_base: unitCostBase });

  /** Write a whole mixture back to the draft, keeping the buyer's price call with it. */
  const setDecision = (next: PlanDecision) => onEdit({ decision: { ...next } });

  const num = (v: string) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  };

  const setStock = (raw: string) => {
    // The per-bin split is scaled from the FRONT: the nearest bins ranked first, so they are
    // the ones kept when the buyer takes less than offered. Same helper the ledger's own
    // per-location inputs use, so a total typed here and quantities typed there agree.
    const edited = applySourceEdits(
      cover,
      sourceEditsForTotal(cover, Math.min(num(raw), stockMax)),
    );
    setDecision({
      ...current,
      skip: undefined,
      stock:
        edited.coverQty > 0
          ? {
              qty: edited.coverQty,
              sources: edited.sources.map((s) => ({
                warehouse_id: s.warehouse_id,
                warehouse_code: s.warehouse_code,
                qty: s.qty,
              })),
            }
          : undefined,
    });
  };

  const setPo = (raw: string) =>
    setDecision({ ...current, skip: undefined, po: Math.min(num(raw), poMax) });

  const [buyDraft, setBuyDraft] = useState<string | null>(null);
  const commitBuy = () => {
    if (buyDraft === null) return;
    // The supplier's MoQ and order multiple do not stop applying because the figure was
    // typed by hand - a buy is rounded wherever it is recorded.
    const rounded = roundBuyQty(num(buyDraft), line.order_qty_inputs);
    setBuyDraft(null);
    setDecision({ ...current, skip: undefined, buy: rounded });
  };

  const level = levelSuggestion;
  const levelAction = level ? levelActionLabel(level) : null;
  const levelValue =
    edit?.level !== undefined
      ? edit.level
      : level
        ? effectiveLevel(level)
        : (line.rec.reorder_level ?? line.rec.master_reorder_level ?? null);
  // The draft, then what the buyer last SAVED (R5), then AutoCount's own master figure.
  // Without the middle term a saved quantity vanished on the next refetch, because the
  // master column is only rewritten by an AutoCount upload.
  const reorderQtyValue =
    edit?.reorderQty !== undefined
      ? edit.reorderQty
      : (level?.reorder_qty ??
         level?.master_reorder_quantity ??
         line.rec.master_reorder_quantity ??
         null);

  const health = healthVerdict(economics, healthWindows);
  const lifecycle =
    edit?.lifecycle !== undefined ? edit.lifecycle : (economics?.lifecycle_decision ?? null);

  const months = level?.basis.months ?? [];

  const pin = useVisibleWidth();

  return (
    // The expanded cell spans the whole TABLE, which is wider than the viewport whenever
    // the grid scrolls - so the fourth zone (Product health) sat past the right edge and
    // reading it meant scrolling the grid sideways and losing the row it belongs to.
    // Pinning the panel to the scroll container's own visible width puts all four zones on
    // screen at once at 1280 and gives 375 a panel that stays put while the columns move.
    <div
      ref={pin.ref}
      className="sticky left-0 border-t bg-muted px-5 py-4"
      style={pin.width ? { width: pin.width } : undefined}
    >
      {lockReason ? (
        <p className="mb-3 text-xs font-medium text-muted-foreground">{lockReason}</p>
      ) : null}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-4">
        {/* ---- 1. Cover ------------------------------------------------------ */}
        <section className="min-w-0 space-y-2">
          <ZoneTitle>Cover</ZoneTitle>

          <NumberField
            label="From stock"
            hint={`pool available ${fmtInt(stockMax)}`}
            value={stockQty}
            max={stockMax}
            disabled={disabled || stockMax <= 0}
            onChange={setStock}
          />
          <NumberField
            label="From PO"
            hint={`open ${fmtInt(poMax)}`}
            value={poQty}
            max={poMax}
            disabled={disabled || poMax <= 0}
            onChange={setPo}
          />
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-muted-foreground">Buy</span>
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              aria-label="Units to buy"
              className="h-7 w-24 text-right tabular-nums"
              disabled={disabled}
              value={buyDraft ?? String(buyQty)}
              onChange={(e) => setBuyDraft(e.target.value)}
              onBlur={commitBuy}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
              }}
            />
          </label>

          {/* R2: a fact, never an input. It is already inside the net and Available. */}
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-muted-foreground">
              SPO arriving
              <span className="ms-1 text-2xs">already in net</span>
            </span>
            <span className="tabular-nums">{fmtInt(line.rec.incoming_spo ?? 0)}</span>
          </div>

          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-muted-foreground">
              MOQ
              {masterMoq === null || masterMoq === undefined ? null : (
                <span className="ms-1 text-2xs">{`master ${fmtInt(masterMoq)}`}</span>
              )}
            </span>
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              aria-label="MOQ"
              className="h-7 w-24 text-right tabular-nums"
              disabled={disabled}
              placeholder={masterMoq === null ? undefined : String(masterMoq)}
              value={moqValue === null || moqValue === undefined ? '' : String(moqValue)}
              onChange={(e) =>
                onEdit({ moq: e.target.value.trim() === '' ? null : num(e.target.value) })
              }
            />
          </label>

          {/* Only when the mixture differs from what was suggested - a hint on every row is
              a hint nobody reads. */}
          {!skipped && gap !== 0 ? (
            <p className="text-2xs text-muted-foreground">
              {gap > 0
                ? `${fmtInt(gap)} over suggested`
                : `${fmtInt(Math.abs(gap))} short of suggested`}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="outline"
              className="h-7"
              disabled={disabled}
              onClick={onUseSuggestion}
            >
              Use suggestion
            </Button>
            <Button
              size="sm"
              variant={skipped ? 'primary' : 'ghost'}
              className="h-7"
              disabled={disabled}
              onClick={() => setDecision({ skip: true })}
            >
              {skipped ? 'Skipped' : 'Skip'}
            </Button>
          </div>
        </section>

        {/* ---- 2. Price and supplier ---------------------------------------- */}
        <section className="min-w-0 space-y-2">
          <ZoneTitle>Price and supplier</ZoneTitle>

          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="text-muted-foreground">Last price</span>
            <span className="min-w-0 text-end">
              {hasPriceOnFile ? (
                <span className="tabular-nums font-medium">
                  {fmtSupplierCost(price?.last?.unit_cost ?? line.unit_cost ?? 0, line.currency)}
                </span>
              ) : (
                <span className="text-muted-foreground">No price on file</span>
              )}
            </span>
          </div>
          {price?.last ? (
            <p className="text-2xs text-muted-foreground">
              {describeLastPurchase(price.last)}
              {price.age_days != null ? ` (${humanAge(price.age_days)})` : ''}
            </p>
          ) : null}

          <div className="space-y-1">
            <Label className="text-2xs text-muted-foreground">Last supplier</Label>
            <SearchableSelect
              size="sm"
              value={supplierCode ?? ''}
              onChange={(code) => onEdit({ supplierCode: code })}
              options={(line.alternatives ?? []).map((a) => ({
                value: a.value,
                label: a.label,
                description: `${fmtSupplierCost(a.unit_cost, a.currency)}${
                  a.lead_time_days > 0 ? `, ${a.lead_time_days} day lead` : ''
                }`,
              }))}
              placeholder="Choose a supplier"
              emptyMessage="No supplier is linked to this product."
              disabled={disabled || (line.alternatives ?? []).length === 0}
              wrapOptions
              triggerClassName="h-7 text-2xs"
            />
          </div>

          {/* The shortlist ranking is demoted to this one line (R6): the price the row is
              costed at is always what we last paid, and a cheaper name is advice, not a swap. */}
          {cheaper ? (
            <p className="flex items-start gap-1 text-2xs text-amber-600">
              <TrendingDown className="mt-0.5 size-3 shrink-0" aria-hidden />
              <span>{`Cheaper on file: ${describeCheaper(cheaper)}`}</span>
            </p>
          ) : null}

          <RadioGroup
            className="flex flex-wrap gap-3 pt-1"
            value={priceMode}
            disabled={disabled}
            onValueChange={(v) => onEdit({ priceMode: v as PlanRowPriceMode })}
          >
            <label className="flex items-center gap-1.5 text-xs">
              <RadioGroupItem value="use_last" id={`price-last-${line.id}`} />
              <span>Use last price</span>
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <RadioGroupItem value="ask_new" id={`price-new-${line.id}`} />
              <span>Get new price</span>
            </label>
          </RadioGroup>

          <p className="text-xs">
            <span className="text-muted-foreground">Line cost </span>
            <span className="tabular-nums font-medium">
              {lineCost === null ? EM_DASH : fmtMoney(lineCost)}
            </span>
            {priceMode === 'use_last' && lineCost !== null ? (
              <span className="text-2xs text-muted-foreground"> at last price</span>
            ) : null}
          </p>
          {price ? null : (
            <p className="text-2xs text-muted-foreground">
              {`Prices older than ${fmtInt(staleAfterDays)} days are treated as stale.`}
            </p>
          )}
        </section>

        {/* ---- 3. AutoCount level + qty ------------------------------------- */}
        <section className="min-w-0 space-y-2">
          <ZoneTitle>AutoCount level + qty</ZoneTitle>

          {levelAction ? (
            <div className="space-y-0.5">
              <Badge variant={levelAction.changed ? 'info' : 'success'} appearance="light" size="sm">
                {levelAction.label}
              </Badge>
              <p className="truncate text-2xs text-muted-foreground" title={levelAction.detail}>
                {levelAction.detail}
              </p>
            </div>
          ) : (
            <p className="text-2xs text-muted-foreground">No level suggestion for this item.</p>
          )}

          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">Level</span>
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              aria-label="AutoCount level"
              className="h-7 w-24 text-right tabular-nums"
              disabled={disabled}
              value={levelValue === null || levelValue === undefined ? '' : String(levelValue)}
              onChange={(e) =>
                onEdit({ level: e.target.value.trim() === '' ? null : num(e.target.value) })
              }
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">Reorder qty</span>
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              aria-label="AutoCount reorder qty"
              className="h-7 w-24 text-right tabular-nums"
              disabled={disabled}
              value={
                reorderQtyValue === null || reorderQtyValue === undefined
                  ? ''
                  : String(reorderQtyValue)
              }
              onChange={(e) =>
                onEdit({ reorderQty: e.target.value.trim() === '' ? null : num(e.target.value) })
              }
            />
          </label>

          {level ? (
            <p className="text-2xs text-muted-foreground">
              {levelTerms(level).map((t) => `${t.label} ${t.value}`).join(' · ')}
            </p>
          ) : null}
          {months.length ? (
            <button
              type="button"
              className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => setChartOpen(true)}
            >
              {`${fmtInt(months.length)}-month chart`}
            </button>
          ) : null}
        </section>

        {/* ---- 4. Product health -------------------------------------------- */}
        <section className="min-w-0 space-y-2">
          <ZoneTitle>Product health</ZoneTitle>

          {health ? (
            <>
              <Badge variant={health.tone} appearance="light" size="sm">
                {health.label}
              </Badge>
              <RadioGroup
                className="flex flex-wrap gap-3"
                value={lifecycle ?? ''}
                disabled={disabled || !economics}
                onValueChange={(v) => onEdit({ lifecycle: v as 'keep' | 'discontinue' })}
              >
                <label className="flex items-center gap-1.5 text-xs">
                  <RadioGroupItem value="keep" id={`health-keep-${line.id}`} />
                  <span>Keep selling</span>
                </label>
                <label className="flex items-center gap-1.5 text-xs">
                  <RadioGroupItem value="discontinue" id={`health-stop-${line.id}`} />
                  <span>Discontinue</span>
                </label>
              </RadioGroup>
              <ul className="space-y-0.5 text-2xs text-muted-foreground">
                {health.factors.map((f) => (
                  <li key={f} className="truncate" title={f}>
                    {f}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-2xs text-muted-foreground">
              No movement on file for this product.
            </p>
          )}
        </section>
      </div>

      {/* The evidence behind the level, moved behind a link so the panel stays one screen
          tall at 1280 (plan 4.4). */}
      <Dialog open={chartOpen} onOpenChange={setChartOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{`What left ${line.sku} each month`}</DialogTitle>
            <DialogDescription className="truncate" title={line.product_name}>
              {line.product_name}
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {months.length ? (
              <ApexChart
                options={{
                  chart: { type: 'bar', toolbar: { show: false } },
                  plotOptions: { bar: { columnWidth: '55%', borderRadius: 2 } },
                  colors: ['var(--color-primary, #2563eb)'],
                  dataLabels: { enabled: true, style: { fontSize: '10px' } },
                  xaxis: { categories: months.map((m) => m.month) },
                  yaxis: { labels: { show: false } },
                  grid: { show: false },
                  tooltip: { enabled: false },
                } satisfies ApexOptions}
                series={[{ name: 'Left this location', data: months.map((m) => m.qty) }]}
                type="bar"
                height={240}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                No monthly movement behind this suggestion.
              </p>
            )}
            {level ? (
              <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
                {`Average ${fmtDecimal(level.basis.adu, 3)} a day over ${fmtInt(level.basis.window_days)} days. Applying the level happens in AutoCount.`}
              </p>
            ) : null}
          </DialogBody>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ZoneTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h4>
  );
}

/** One capped quantity input. The cap is SHOWN, never only enforced: an input that silently
 *  clamps reads as broken. */
function NumberField({
  label,
  hint,
  value,
  max,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  max: number;
  disabled?: boolean;
  onChange: (raw: string) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="min-w-0 truncate text-muted-foreground" title={`${label} (${hint})`}>
        {label}
        <span className="ms-1 text-2xs">{`(${hint})`}</span>
      </span>
      <Input
        type="number"
        min={0}
        max={max}
        inputMode="numeric"
        aria-label={label}
        className="h-7 w-24 text-right tabular-nums"
        disabled={disabled}
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}


/**
 * The width of the nearest horizontally-scrolling ancestor, so a full-width row can be
 * pinned to what the reader can actually SEE rather than to the table's own width.
 *
 * A `colSpan` cell is as wide as every column together, and this grid is `width: fixed`
 * with eleven of them - so at any viewport narrower than the table, content at the right
 * of the panel is simply off screen. `position: sticky; left: 0` keeps it in place while
 * the columns scroll under it, and the measured width is what stops it stretching to the
 * table's width again.
 *
 * Measured rather than assumed: the sidebar collapses, the window resizes, and a hard-coded
 * breakpoint would be wrong in exactly the cases this exists for.
 */
function useVisibleWidth(): { ref: (node: HTMLDivElement | null) => void; width: number | null } {
  const [width, setWidth] = useState<number | null>(null);
  const observed = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: HTMLDivElement | null) => {
    observed.current?.disconnect();
    observed.current = null;
    if (!node) return;
    let parent: HTMLElement | null = node.parentElement;
    while (parent) {
      const overflow = getComputedStyle(parent).overflowX;
      if (overflow === 'auto' || overflow === 'scroll') break;
      parent = parent.parentElement;
    }
    if (!parent) return;
    const measure = () => setWidth(parent.clientWidth || null);
    measure();
    // jsdom has no ResizeObserver; the measurement above still runs, which is all a
    // component test needs.
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    observed.current = observer;
  }, []);

  useEffect(() => () => observed.current?.disconnect(), []);

  return { ref, width };
}
