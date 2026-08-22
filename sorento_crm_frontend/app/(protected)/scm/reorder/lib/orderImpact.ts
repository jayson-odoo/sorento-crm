/**
 * Summary Order Report - PURE consequence maths (AC-C2.7). No React, no fetching.
 *
 * The rule this file exists to hold: **a chosen quantity above the shortfall is
 * not a warning state.** Ordering spare is routine and often correct, so the
 * screen's job is to state what the number MEANS, not to argue with it:
 * shortfall covered, spare created and where it lands, resulting months of
 * cover, cash committed, and container volume added.
 *
 * The second rule, which is the reason every figure is nullable: **a missing
 * input is named, never zeroed.** Months of cover is derivable for 62% of the
 * book (it needs `scm.demand_stat.avg_daily_demand`) and container volume for
 * 16% (it needs recorded product dimensions). Printing 0 for the rest would read
 * as "already out of stock" and "no space needed", which are decisions taken on
 * a figure nobody measured. Each figure therefore carries either a value or the
 * name of the input that is not recorded, and the panel renders whichever it
 * got. Same rule the transfer proposals in `CoverageTimelinePanel` follow for an
 * unconfigured transfer cost or lead time.
 *
 * Survives Phase 2. Only `summaryOrderMockStore.ts` is deleted.
 */
import { fmtDecimal, fmtSupplierCost } from '../../lib/format';
import type { OrderSummaryRow, SupplierCandidate } from '../types/summaryOrder.types';

/** Days per month used to turn a daily demand rate into months of cover. */
export const DAYS_PER_MONTH = 30;

/**
 * One figure in the consequence panel. Exactly one of `value` / `missing` is set.
 * `missing` names the input that is not recorded, in the words the person who
 * could go and record it would use.
 */
export interface ImpactFigure {
  value: number | null;
  missing: string | null;
}

function known(value: number): ImpactFigure {
  return { value, missing: null };
}

function unknown(missing: string): ImpactFigure {
  return { value: null, missing };
}

/** What a chosen order quantity does. Every field is display-ready. */
export interface OrderQuantityImpact {
  /** The dated shortfall the decision is being taken against. */
  shortfall: number;
  /** How much of that shortfall the chosen quantity covers. */
  shortfall_covered: number;
  /** What is still short after it. Zero once the shortfall is met. */
  shortfall_remaining: number;
  /** Everything above the shortfall. Spare, not an error. */
  spare_qty: number;
  /** The pool the spare lands in. Null when the row does not name one. */
  spare_lands_at: string | null;
  /** Net position after the buy, divided by the monthly demand rate. */
  months_of_cover: ImpactFigure;
  /** Chosen quantity times the supplier's ex-works unit cost. */
  cash_committed: ImpactFigure;
  /** Currency the cash figure is quoted in. Null when there is no cost. */
  currency: string | null;
  /** Chosen quantity times the unit volume, in cubic metres. */
  volume_cbm: ImpactFigure;
}

/**
 * The net position after the buy: what is on hand plus everything inbound plus
 * the chosen quantity, less everything committed. This is the figure months of
 * cover is quoted against, so the cover a person reads is the cover the order
 * actually produces.
 */
export function positionAfterBuy(row: OrderSummaryRow, chosenQty: number): number {
  return (
    row.on_hand +
    row.qty_on_order +
    row.qty_in_transit +
    chosenQty -
    row.project_demand -
    row.retail_outstanding
  );
}

/**
 * State what a chosen quantity means (AC-C2.7).
 *
 * `supplier` is the candidate the buyer picked; null before they pick one, which
 * is why the cash figure names the missing input rather than assuming a cost.
 */
export function orderQuantityImpact(
  row: OrderSummaryRow,
  chosenQty: number,
  supplier: SupplierCandidate | null,
): OrderQuantityImpact {
  const qty = Number.isFinite(chosenQty) && chosenQty > 0 ? chosenQty : 0;
  const covered = Math.min(qty, row.shortfall);
  const spare = Math.max(0, qty - row.shortfall);

  const rate = row.avg_daily_demand;
  const monthsOfCover =
    rate && rate > 0
      ? known(positionAfterBuy(row, qty) / (rate * DAYS_PER_MONTH))
      : unknown('demand rate not recorded');

  const unitCost = supplier?.last_po_cost ?? null;
  const cash =
    unitCost === null
      ? unknown(supplier ? 'no cost on record for this supplier' : 'no supplier chosen yet')
      : known(qty * unitCost);

  const volume =
    row.unit_volume_cbm === null
      ? unknown('dimensions not recorded')
      : known(qty * row.unit_volume_cbm);

  return {
    shortfall: row.shortfall,
    shortfall_covered: covered,
    shortfall_remaining: Math.max(0, row.shortfall - qty),
    spare_qty: spare,
    spare_lands_at: row.spare_lands_at,
    months_of_cover: monthsOfCover,
    cash_committed: cash,
    currency: unitCost === null ? null : (supplier?.currency ?? null),
    volume_cbm: volume,
  };
}

/**
 * A cost in the supplier's own currency (AC-C3.4), for the loading-plan table.
 *
 * Delegates to the shared `fmtSupplierCost` so there is one answer to "how is a supplier
 * price written", and keeps its own empty-string-for-null convention because this one
 * renders inside a dense grid cell where an em dash is noise.
 */
export function fmtCost(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined) return '';
  return fmtSupplierCost(value, currency);
}

/** A signed variance, so a supplier that repriced upward reads as `+`. */
export function fmtVariance(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined) return '';
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}${fmtCost(Math.abs(value), currency)}`;
}

/** Cubic metres, to one decimal. */
export function fmtCbm(value: number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return `${fmtDecimal(value, 1)} m3`;
}

/** Months of cover, to one decimal. */
export function fmtMonths(value: number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return `${fmtDecimal(value, 1)} months`;
}
