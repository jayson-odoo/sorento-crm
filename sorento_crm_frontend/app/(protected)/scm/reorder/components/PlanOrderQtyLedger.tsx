'use client';

import { useEffect, useRef, useState } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { EM_DASH, fmtDecimal, fmtInt, fmtSigned } from '../../lib/format';
import { DrillHeader } from './PlanExplainDrills';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import {
  applySourceEdits,
  defaultSourceEdits,
  maxSourceEdit,
  type CoverProposal,
  type SourceEdits,
} from '../lib/coverPlan';
import { describePoBook, type PoReceipt } from '../lib/poCover';
import { moqGap, moqGapNote, type ProductEconomics } from '../lib/productHealth';
import {
  clampForecastQty,
  composeMixture,
  daysTerm,
  forecastAddOn,
  forecastQtyCap,
  levelLine,
  lineBreachStatus,
  roundBuyQty,
} from '../lib/orderQtyLedger';
import type { TrajectoryEntry } from '../lib/trajectory';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * The order-qty ledger (S3, UAC B): the same three blocks the design session sketched -
 * THE LINE, COVER BEFORE BUYING, THE BUY - replacing the old order-qty drill behind the
 * "Explain order qty" trigger the Suggested-qty column already opens.
 *
 * Blocks two and three read and write the SAME decision state the Decision cell and the
 * Adjust dialog use (`coverForLine` / `poOffset`, S16) - there is no second, parallel model
 * of what a line's buy is made of, and toggling a cover part here commits through `onDecide`
 * exactly as accepting or adjusting does. That is also why there is no separate "Record"
 * button (UAC B4): the toggle IS the edit.
 */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-t bg-muted/40 px-3 py-1.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}

function KVRow({
  label,
  value,
  note,
  muted,
}: {
  label: string;
  value: string;
  note?: string;
  muted?: boolean;
}) {
  return (
    <div className={`flex items-baseline justify-between gap-3 text-xs ${muted ? 'text-muted-foreground' : ''}`}>
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end">
        <span className="tabular-nums">{value}</span>
        {note ? <span className="ms-1.5 text-2xs text-muted-foreground">{note}</span> : null}
      </span>
    </div>
  );
}

/** A cover part the buyer can turn off or back on - the ONE editing surface this ledger
 *  offers, and the reason a separate Adjust popup is not needed for this operation.
 *
 * Unticked reads as plain muted text, never strikethrough (user feedback, 2026-08-12) -
 * strikethrough is reserved for `disabled`, the one case where the line names something
 * the buyer cannot actually toggle (a trend that zeroed the add-on out). */
function ToggleLine({
  checked,
  onToggle,
  label,
  title,
  disabled,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-start gap-2 text-xs ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
      title={title}
    >
      <Checkbox
        size="sm"
        checked={checked}
        onCheckedChange={onToggle}
        disabled={disabled}
        className="mt-0.5"
      />
      <span
        className={
          checked
            ? 'font-medium'
            : disabled
              ? 'text-muted-foreground line-through'
              : 'text-muted-foreground'
        }
      >
        {label}
      </span>
    </label>
  );
}

/**
 * The forecast add-on's own row: a tick to opt in, plus the buyer's own editable figure
 * (user feedback, 2026-08-12: "what if I don't want to buy 1,200 more, what if 1,500?
 * editable here"). The number is not inside the checkbox's own `<label>` - a native label
 * click delegates to its first form control, which would toggle the checkbox every time
 * the buyer clicked into the input to edit it - so the checkbox and the input are two
 * independent controls, each with its own accessible name.
 */
function ForecastAddOnLine({
  checked,
  onToggle,
  qty,
  onQtyChange,
  cap,
  detail,
}: {
  checked: boolean;
  onToggle: () => void;
  qty: number;
  onQtyChange: (value: number) => void;
  cap: number;
  detail: string;
}) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <Checkbox
        size="sm"
        checked={checked}
        onCheckedChange={onToggle}
        className="mt-0.5"
        aria-label={checked ? `Added ${fmtInt(qty)}` : `Add ${fmtInt(qty)}`}
      />
      <div className="min-w-0 flex-1 space-y-0.5">
        <div
          className={`flex flex-wrap items-baseline gap-1.5 ${checked ? 'font-medium' : 'text-muted-foreground'}`}
        >
          <span>{checked ? 'Added' : '+ Add'}</span>
          <Input
            type="number"
            variant="sm"
            min={0}
            max={cap}
            step={1}
            value={qty}
            onChange={(e) => onQtyChange(e.target.valueAsNumber)}
            className="h-6 w-20 tabular-nums"
            aria-label="Forecast add-on quantity"
          />
        </div>
        <p className="text-2xs text-muted-foreground">{`(${detail})`}</p>
      </div>
    </div>
  );
}

/**
 * One offered location and how much of it to use.
 *
 * > "why am I allowed to use stock from other locations? ... use stock should behave like the
 * >  top-up purchase control - a toggle, and when on, editable per-location quantities
 * >  feeding the buy qty."
 *
 * The same two-control shape as `ForecastAddOnLine`, and for the same reason: the number is
 * NOT inside a `<label>` wrapping a checkbox, so clicking into the input to edit it cannot
 * toggle anything. What is free at that location sits beside the input rather than only in
 * the `max` attribute, because a cap the buyer cannot see reads as the field being broken.
 */
function CoverSourceLine({
  code,
  free,
  max,
  qty,
  onQtyChange,
}: {
  code: string;
  /** What the location holds - a fact about the location, stated as such. */
  free: number;
  /** What this field may actually be set to: `free`, capped by what the row still needs. */
  max: number;
  qty: number;
  onQtyChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="min-w-0 flex-1 truncate" title={code}>
        {code}
      </span>
      <span className="shrink-0 text-2xs tabular-nums text-muted-foreground">
        {`${fmtInt(free)} free`}
      </span>
      <Input
        type="number"
        variant="sm"
        min={0}
        max={max}
        step={1}
        value={qty}
        onChange={(e) => onQtyChange(e.target.valueAsNumber)}
        className="h-6 w-20 shrink-0 tabular-nums"
        aria-label={`Use from ${code}`}
      />
    </div>
  );
}

/** THE LINE, auto mode: the ROP derivation, unchanged copy from the old order-qty drill -
 *  safety stock, reorder point, order-up-to, and where the daily rate comes from. MoQ /
 *  order multiple moved to THE BUY block (UAC B6) and no longer render here. */
function AutoDerivation({ line }: { line: PlanLine }) {
  const q = line.order_qty_inputs;
  const rec = line.rec;
  // A pooled buy is sized once for every location that shares stock, then split. Saying
  // so is the difference between "why 55" answering itself and the reader doing
  // arithmetic that cannot work (ported from the old order-qty drill, PlanExplainDrills'
  // `OrderQtyDrill`, when the S3 ledger replaced it - the ledger had dropped this half).
  const alloc = rec.allocation ?? [];
  const pooled = alloc.length > 1;
  const demandRate = line.forecast_daily_demand;
  const leadDays = line.supplier.lead_time_days;
  const reviewTerm = daysTerm(rec.review_days, 'review');
  const leadTerm = daysTerm(leadDays, 'lead');
  return (
    <>
      <div className="space-y-1 px-3 py-2">
        <KVRow label="Safety stock" value={q.safety_stock === null ? EM_DASH : fmtInt(q.safety_stock)} />
        <KVRow
          label={pooled ? 'Order-up-to level (whole pool)' : 'Order-up-to level'}
          value={q.order_up_to === null ? EM_DASH : fmtInt(q.order_up_to)}
        />
      </div>
      {pooled ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Bought for the whole pool
          </div>
          <p className="text-2xs text-muted-foreground">
            One purchase covers {alloc.length} locations that share stock. It is sized once
            against the pool, then placed where the shortage is.
          </p>
          <div className="mt-1 space-y-0.5">
            {alloc.map((a) => (
              <div key={a.warehouse_code ?? String(a.qty)} className="flex justify-between text-2xs">
                <span
                  className={
                    a.warehouse_code === rec.warehouse_code ? 'font-medium' : 'text-muted-foreground'
                  }
                >
                  {a.warehouse_code ?? EM_DASH}
                </span>
                <span className="tabular-nums">{fmtInt(a.qty)}</span>
              </div>
            ))}
            <div className="mt-1 flex justify-between border-t pt-1 text-2xs font-medium">
              <span>Pool total</span>
              <span className="tabular-nums">{fmtInt(alloc.reduce((t, a) => t + (a.qty ?? 0), 0))}</span>
            </div>
          </div>
        </div>
      ) : null}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Order-up-to level
        </div>
        <p className="text-2xs text-muted-foreground">S = reorder point + demand rate x review period</p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          {reviewTerm ? (
            <span className="tabular-nums text-muted-foreground">
              {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)} +{' '}
              {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x {reviewTerm}
            </span>
          ) : (
            <span className="text-muted-foreground">no review period set</span>
          )}
          <span className="tabular-nums font-semibold">
            {q.order_up_to === null ? EM_DASH : fmtInt(q.order_up_to)}
          </span>
        </div>
        {rec.safety_days != null && rec.review_days != null ? (
          <p className="mt-1 text-2xs text-muted-foreground">
            {fmtInt((rec.safety_days ?? 0) + (leadDays ?? 0) + (rec.review_days ?? 0))} days of cover (
            {fmtInt(rec.safety_days)} safety + {fmtInt(leadDays)} lead + {fmtInt(rec.review_days)} review)
          </p>
        ) : null}
      </div>
      {demandRate != null && rec.demand_window_days ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Where the rate comes from
          </div>
          <p className="text-2xs text-muted-foreground">
            {fmtInt(demandRate * rec.demand_window_days)} units left this location over the last{' '}
            {fmtInt(rec.demand_window_days)} days, which averages {fmtDecimal(demandRate)} a day. Past
            deliveries, not the open orders.
          </p>
        </div>
      ) : null}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Reorder point
        </div>
        <p className="text-2xs text-muted-foreground">ROP = safety stock + demand rate x lead time</p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          {leadTerm ? (
            <span className="tabular-nums text-muted-foreground">
              {q.safety_stock === null ? EM_DASH : fmtDecimal(q.safety_stock)} +{' '}
              {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x {leadTerm}
            </span>
          ) : (
            <span className="text-muted-foreground">no lead time on file</span>
          )}
          <span className="tabular-nums font-semibold">
            {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)}
          </span>
        </div>
      </div>
    </>
  );
}

/** THE LINE, manual mode: the level the buyer owns, its source, and (when the backend ever
 *  carries it) when it was set - not the ROP formula, which no longer decides anything on
 *  this basis. */
function ManualLevelLine({ rec }: { rec: ReorderRecommendation }) {
  const lvl = levelLine(rec);
  return (
    <div className="space-y-1 px-3 py-2">
      <KVRow label="Reorder level" value={lvl.level === null ? EM_DASH : fmtInt(lvl.level)} />
      <p className="text-2xs text-muted-foreground">
        {lvl.sourceLabel}
        {lvl.setAt ? `, set ${lvl.setAt}` : ''}
      </p>
    </div>
  );
}

export function OrderQtyLedger({
  line,
  decision,
  cover,
  poReceipts,
  economicsFor,
  healthThresholds,
  trend,
  onDecide,
}: {
  line: PlanLine;
  decision: PlanDecision | undefined;
  /** What the plan suggests: buy it, cover it from elsewhere, or both - the SAME proposal
   *  the Decision cell reads. */
  cover: CoverProposal;
  poReceipts: PoReceipt[];
  economicsFor?: (line: PlanLine) => ProductEconomics | undefined;
  healthThresholds: { margin_floor_pct: number; dead_turnover_months: number };
  /** The SAME trajectory entry that drives the row's own Trend pill, so the forecast
   *  add-on's rising/falling read never disagrees with it. */
  trend?: TrajectoryEntry;
  onDecide: (next: PlanDecision) => void;
}) {
  const rec = line.rec;
  const q = line.order_qty_inputs;
  const manual = rec.policy_type === 'reorder_level';
  const needed = Math.ceil(line.order_qty);
  const poQty = poReceipts.reduce((t, r) => t + r.remaining, 0);

  // Which cover parts are "on": the committed decision when one exists, the engine's own
  // suggested mixture otherwise - never a third guess (UAC B4).
  //
  // `stockOn` is LOCAL state, seeded once, exactly as `forecastOn` below is: it is the
  // buyer's intention, not a reading of the numbers. Deriving it from the decision meant
  // that zeroing every location (a normal step while moving units between them) read as
  // "cover is off" and unmounted the inputs from under the buyer mid-edit. Cover 0 with the
  // toggle ON is a legitimate state: the whole gap is bought, and the rows stay there.
  const [stockOn, setStockOn] = useState(() =>
    decision ? (decision.stock?.qty ?? 0) > 0 : cover.coverQty > 0,
  );
  const poOn = decision ? (decision.po ?? 0) > 0 : poQty > 0;
  // How much to take from EACH offered location. Seeded from the decision already taken, or
  // from the engine's proposal (same-segment first) - so a buyer who never touches these
  // inputs gets exactly today's answer (UAC AC-3.5).
  const seedEdits = (): SourceEdits => {
    const taken = decision?.stock?.sources;
    if (taken?.length) {
      const base: Record<string, number> = Object.fromEntries(
        cover.offered.map((s) => [s.warehouse_id, 0]),
      );
      for (const s of taken) base[s.warehouse_id] = s.qty;
      return base;
    }
    return defaultSourceEdits(cover);
  };
  const [sourceEdits, setSourceEdits] = useState<SourceEdits>(seedEdits);
  // Re-seed when the OFFER itself changes - another row's decision can free a location up or
  // spend it down while this popover is open, and a newly offered location left out of the
  // edits map would silently render as 0 with no way to tell it from a deliberate zero. The
  // key deliberately excludes this row's own take (usePlanLines hands its own units back),
  // so committing an edit here never re-seeds over the buyer's typing.
  const offerKey = cover.offered.map((s) => `${s.warehouse_id}:${s.qty}`).join('|');
  const seededFor = useRef(offerKey);
  useEffect(() => {
    if (seededFor.current === offerKey) return;
    seededFor.current = offerKey;
    setSourceEdits(seedEdits());
    // `seedEdits` closes over the current cover/decision, which is what a re-seed wants.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offerKey]);
  const edited = applySourceEdits(cover, sourceEdits);
  // The forecast add-on has no home in `PlanDecision` beyond the buy total it grows, so its
  // own on/off state is re-derived from the reason a previous toggle left behind (best
  // effort - a manual Adjust afterwards can still overwrite that reason, which is fine: the
  // add-on is offered fresh, never assumed).
  const [forecastOn, setForecastOn] = useState(() => Boolean(decision?.reason?.startsWith('Forecast:')));

  const mixture = composeMixture(needed, cover, poQty, {
    stockOn,
    poOn,
    stockQty: edited.coverQty,
  });
  // The SAME trajectory verdict that drives the row's own Trend pill - a rising line never
  // sees a flat proposal here while its pill says "consider more" (S3 follow-up).
  const addOn = forecastAddOn(rec, trend);
  // The buyer's own figure for the add-on, editable regardless of tick state (user
  // feedback, 2026-08-12: "what if I don't want to buy 1,200 more, what if 1,500?
  // editable here"). The trend-aware proposal is only ever the STARTING value - once the
  // popover mounts, the buyer's typed figure is the one that gets applied.
  const [forecastQty, setForecastQty] = useState<number>(() => addOn?.qty ?? 0);
  const forecastCap = forecastQtyCap(addOn?.qty ?? 0);
  // `qty` can be 0 (a falling trend ate the whole flat proposal) - that renders a disabled
  // line, never a checkbox, so it can never actually be toggled on.
  const delta = forecastOn ? forecastQty : 0;
  const buyBeforeRounding = mixture.buy + delta;
  const buyRounded = roundBuyQty(buyBeforeRounding, q);
  const econ = economicsFor?.(line);
  const gap = moqGap(buyBeforeRounding, q.moq, buyRounded, econ, healthThresholds.dead_turnover_months);
  // Whether the row's own basis (level or ROP) is actually breached right now, computed
  // honestly off `net` - never trusted off `rec_type` alone (S3 follow-up bug: a covered
  // row well above its line showed a bogus "Gap to line").
  const breach = lineBreachStatus(rec, line.net);
  const showLineStatus = rec.type === 'covered' && !breach.breached && breach.basisLabel !== null;
  // The parenthetical shared between the toggle's own label and the reason recorded when
  // it is applied, so the two surfaces never drift (Fix2/Fix3: name the horizon's source,
  // and the trend read behind it, in one place). Describes WHY the system proposed a
  // figure, not the buyer's own typed number - that lives beside it, not inside it.
  const addOnDetail = (a: NonNullable<typeof addOn>) =>
    `next ${a.horizonDays}d demand at ${fmtDecimal(a.ratePerDay)}/day - ${a.sourceLabel}${
      a.trendNote ? `, ${a.trendNote}` : ''
    }`;

  const commit = (next: {
    stockOn: boolean;
    poOn: boolean;
    forecastOn: boolean;
    forecastQty: number;
    edits: SourceEdits;
  }) => {
    // The per-location figures ARE the split that gets recorded - the ledger never writes
    // the proposal's own sources back over an edit the buyer just made.
    const stock = applySourceEdits(cover, next.edits);
    const m = composeMixture(needed, cover, poQty, { ...next, stockQty: stock.coverQty });
    const d = next.forecastOn ? next.forecastQty : 0;
    const before = m.buy + d;
    // The SAME helper the Accept button and the Adjust popup record through, so the three
    // surfaces cannot land on different quantities for one row (review finding 1, round 2).
    const rounded = roundBuyQty(before, q);
    onDecide({
      ...(rounded > 0 ? { buy: rounded } : {}),
      ...(m.stockQty > 0
        ? {
            stock: {
              qty: m.stockQty,
              sources: stock.sources.map((s) => ({
                warehouse_id: s.warehouse_id,
                warehouse_code: s.warehouse_code,
                qty: s.qty,
              })),
            },
          }
        : {}),
      ...(m.usePo > 0 ? { po: m.usePo } : {}),
      ...(next.forecastOn && addOn
        ? { reason: `Forecast: +${fmtInt(next.forecastQty)} (${addOnDetail(addOn)})` }
        : {}),
    });
  };

  const toggleStock = () => {
    const next = !stockOn;
    setStockOn(next);
    commit({ stockOn: next, poOn, forecastOn, forecastQty, edits: sourceEdits });
  };
  const togglePo = () => commit({ stockOn, poOn: !poOn, forecastOn, forecastQty, edits: sourceEdits });
  const toggleForecast = () => {
    const next = !forecastOn;
    setForecastOn(next);
    commit({ stockOn, poOn, forecastOn: next, forecastQty, edits: sourceEdits });
  };
  // Editing a location re-applies immediately, exactly as the forecast input does: the
  // input IS the edit, there is no separate Record step in this ledger (UAC B4).
  const changeSourceQty = (warehouseId: string, raw: number) => {
    // What the LOCATION holds free, and what the ROW still needs once the other locations are
    // counted - the second half was missing, so 40 could be typed against a gap of 10 and the
    // 30 units this row could never use were withdrawn from every other row of the product.
    const max = maxSourceEdit(cover, warehouseId, sourceEdits);
    const clamped = Number.isFinite(raw) ? Math.max(0, Math.min(max, Math.floor(raw))) : 0;
    const edits = { ...sourceEdits, [warehouseId]: clamped };
    setSourceEdits(edits);
    if (stockOn) commit({ stockOn, poOn, forecastOn, forecastQty, edits });
  };
  // Editing while ticked re-applies immediately - the input IS the edit, there is no
  // separate "Record" step (mirrors the ledger's own UAC B4 non-goal for the toggles).
  const changeForecastQty = (raw: number) => {
    const clamped = clampForecastQty(raw, forecastCap);
    setForecastQty(clamped);
    if (forecastOn) commit({ stockOn, poOn, forecastOn, forecastQty: clamped, edits: sourceEdits });
  };

  const noCoverAvailable = cover.coverQty <= 0 && poQty <= 0;
  const collapsed = buyBeforeRounding <= 0;
  const poLabel =
    poReceipts.length === 1 ? poReceipts[0].po_number : `${poReceipts.length} open orders`;

  return (
    <div>
      <DrillHeader title={`Order qty = ${fmtInt(line.order_qty)}`} />
      {/* Scrolls INSIDE the popover rather than overflowing the viewport - the ledger has
          grown to three blocks, and a 375px screen has no room to spare (S3). */}
      <div className="max-h-[70vh] overflow-y-auto">
        <div className="pb-1">
          <SectionLabel>The line</SectionLabel>
          {manual ? <ManualLevelLine rec={rec} /> : <AutoDerivation line={line} />}

          <div className="space-y-1 border-t px-3 py-2">
            <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
              Net now
            </div>
            <KVRow label="On hand" value={fmtInt(rec.on_hand ?? 0)} />
            <KVRow label="+ SPO (arriving)" value={fmtInt(rec.incoming_spo ?? 0)} />
            {/* PO is counted here now (21 Aug fix) - the sizing engine nets the open PO
                book into the same `net` this row was decided against, so a leg reading
                "not counted" would be stating something that stopped being true. */}
            {(rec.outstanding_po ?? 0) > 0 ? (
              <KVRow label="+ PO (open)" value={fmtInt(rec.outstanding_po)} />
            ) : null}
            <KVRow label="- SO (outstanding)" value={fmtInt(rec.outstanding_sales ?? 0)} />
            <div className="mt-1 flex justify-between border-t pt-1 text-xs font-medium">
              <span>Net</span>
              <span className="tabular-nums">{fmtSigned(line.net)}</span>
            </div>
          </div>

          {showLineStatus ? (
            <>
              {/* The line reads ABOVE its own basis - the old "Gap to line" figure here was
                  never a shortfall, it was the engine's own covered committed demand, and
                  labelling it "gap" read as a bug (net 135, level 120, "gap" 15?). */}
              <div className="border-t px-3 py-2">
                <p className="text-xs text-muted-foreground">
                  {`Line not breached - net ${fmtSigned(line.net)} above ${breach.basisLabel} ${fmtInt(
                    breach.basisValue,
                  )}`}
                </p>
              </div>
              <div className="border-t px-3 py-2">
                <p className="text-xs text-muted-foreground">
                  {`Committed demand ${
                    rec.covered_committed == null ? EM_DASH : fmtInt(rec.covered_committed)
                  }, covered by stock`}
                </p>
              </div>
            </>
          ) : (
            <div className="border-t px-3 py-2">
              <KVRow
                label="Gap to line"
                value={rec.recommended_qty == null ? EM_DASH : fmtInt(rec.recommended_qty)}
              />
            </div>
          )}

          <SectionLabel>Cover before buying</SectionLabel>
          <div className="space-y-2 px-3 py-2">
            {noCoverAvailable ? (
              <p className="text-xs text-muted-foreground">
                No cover available - full quantity must be bought
              </p>
            ) : (
              <>
                {cover.coverQty > 0 ? (
                  <div className="space-y-1.5">
                    <ToggleLine
                      checked={stockOn}
                      onToggle={toggleStock}
                      label={
                        stockOn
                          ? `Use stock ${fmtInt(edited.coverQty)}`
                          : `Use stock ${fmtInt(cover.coverQty)} (${cover.sources
                              .map((s) => s.warehouse_code)
                              .join(', ')})`
                      }
                    />
                    {/* On, the sources stop being a sentence and become the edit surface: one
                        row per location the policy allows this row to draw on. Off, they are
                        not offered at all - cover is 0 and the whole gap is bought. */}
                    {stockOn ? (
                      <div className="ms-6 space-y-1">
                        {cover.offered.map((s) => (
                          <CoverSourceLine
                            key={s.warehouse_id}
                            code={s.warehouse_code}
                            free={s.qty}
                            max={maxSourceEdit(cover, s.warehouse_id, sourceEdits)}
                            qty={sourceEdits[s.warehouse_id] ?? 0}
                            onQtyChange={(v) => changeSourceQty(s.warehouse_id, v)}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {poQty > 0 ? (
                  <ToggleLine
                    checked={poOn}
                    onToggle={togglePo}
                    label={`Use PO ${poLabel} ${fmtInt(poQty)}`}
                    title={describePoBook(poReceipts).join('\n')}
                  />
                ) : null}
              </>
            )}
            {/* SPO is inside Net already (Block 1) - never re-offered as a choice, only
                restated so the buyer sees where it went (UAC B3). Shown regardless of
                whether there is any cover to toggle, since it is a fact, not a part. */}
            {(rec.incoming_spo ?? 0) > 0 ? (
              <p className="text-2xs text-muted-foreground">
                {`SPO arriving ${fmtInt(rec.incoming_spo ?? 0)} - already counted`}
              </p>
            ) : null}
          </div>

          <SectionLabel>The buy</SectionLabel>
          <div className="space-y-2 px-3 py-2">
            {addOn && addOn.qty > 0 ? (
              <ForecastAddOnLine
                checked={forecastOn}
                onToggle={toggleForecast}
                qty={forecastQty}
                onQtyChange={changeForecastQty}
                cap={forecastCap}
                detail={addOnDetail(addOn)}
              />
            ) : null}
            {/* A falling trend can eat the whole flat proposal (floored at 0) - stated
                rather than silently offering nothing, so the buyer sees WHY there is no
                add-on to opt into here (Fix3). */}
            {addOn && addOn.qty === 0 ? (
              <p className="text-xs text-muted-foreground">Orders falling - no add-on proposed</p>
            ) : null}
            {collapsed ? (
              <p className="text-xs text-muted-foreground">Nothing to buy - MoQ not relevant</p>
            ) : (
              <>
                <KVRow label="Buy before rounding" value={fmtInt(buyBeforeRounding)} />
                <div className="flex justify-between border-t pt-1 text-xs font-medium">
                  <span>MoQ / order multiple</span>
                  <span className="tabular-nums">{fmtInt(buyRounded)}</span>
                </div>
                {gap ? (
                  <p
                    className={`text-2xs ${gap.verdict === 'clears' ? 'text-muted-foreground' : 'text-scm-overstock'}`}
                  >
                    {moqGapNote(gap, fmtInt)}
                  </p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
