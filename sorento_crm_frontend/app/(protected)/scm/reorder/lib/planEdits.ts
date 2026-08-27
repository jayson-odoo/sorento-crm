/**
 * A plan row's DRAFT edit, and the words the collapsed row says about it.
 *
 * The revamp moves every per-row write off its own control and behind ONE Save: the panel's
 * inputs (cover mix, MOQ, AutoCount level, reorder qty, price call, supplier, keep/discontinue)
 * write here, into a map the page holds, and nothing reaches the backend until Save runs
 * (plan 4.5). That is the whole difference from the previous screen, where a pencil Record, a
 * MOQ blur, a level Save and a health click each fired their own request.
 *
 * Keyed by ROW id, not recommendation id: a product-grain run renders one row per product
 * (`planLineGrouping.ts`), and the edit belongs to that row. The save fans it out to every
 * member recommendation exactly as `usePlanLines.decide` / `.updateMoq` already do.
 */
import { roundBuyQty } from './orderQtyLedger';
import { NO_COVER, type CoverProposal } from './coverPlan';
import { poOffset, type PoReceipt } from './poCover';
import type { PlanLine } from './planLine';
import { decidedCost, groupDecisionState, type PlanDecision, type PlanDecisionMap } from './planDecisions';
import { isGroupedLine } from './planLineGrouping';
import { fmtInt } from '../../lib/format';
import type { PlanRowPriceMode } from '../types/decisions.types';

/** One row's unsaved edit. Every field is optional: a row nobody touched has no entry. */
export interface PlanRowEdit {
  /** The cover mixture (buy / stock / PO / skip), as the panel's three inputs left it. */
  decision?: PlanDecision;
  /** The buyer's own MOQ, or null to withdraw an override back to the master figure. */
  moq?: number | null;
  /** The AutoCount level to set, or null to withdraw an amendment. */
  level?: number | null;
  /** The AutoCount reorder quantity to set, or null to withdraw one (R5). */
  reorderQty?: number | null;
  /** Keep selling / discontinue, or null to withdraw the answer. */
  lifecycle?: 'keep' | 'discontinue' | null;
  /** Use the last price, or ask for a new one. Rides on the decision when saved. */
  priceMode?: PlanRowPriceMode;
  /** The supplier code the buyer picked. Rides on the decision when saved. */
  supplierCode?: string;
}

export type PlanRowEditMap = Readonly<Record<string, PlanRowEdit | undefined>>;

/** Whether an edit says anything at all. An entry that only ever held cleared fields is not
 *  an edit, and must not count towards Save (N). */
export function hasRowEdit(edit: PlanRowEdit | undefined): boolean {
  if (!edit) return false;
  return (
    edit.decision !== undefined ||
    edit.moq !== undefined ||
    edit.level !== undefined ||
    edit.reorderQty !== undefined ||
    edit.lifecycle !== undefined ||
    edit.priceMode !== undefined ||
    edit.supplierCode !== undefined
  );
}

/**
 * The engine's own mixture for a line: stock first (what is already free), then the open PO
 * book, then a buy for what is left, rounded to the supplier's MOQ and order multiple.
 *
 * Lifted out of the old decision cell so the pill, the panel and Confirm all read ONE
 * derivation - a button that says 14 and records 20 was the worse half of that bug.
 */
export function suggestedDecisionFor(
  line: PlanLine,
  cover: CoverProposal = NO_COVER,
  poReceipts: PoReceipt[] = [],
): PlanDecision {
  const needed = Math.ceil(line.order_qty);
  const stockQty = cover.coverQty;
  const afterStock = stockQty > 0 ? cover.buyQty : needed;
  const poQty = poReceipts.reduce((t, r) => t + r.remaining, 0);
  const { usePo, buy } = poOffset(afterStock, poQty);
  const buyQty = roundBuyQty(buy, line.order_qty_inputs);
  return {
    ...(buyQty > 0 ? { buy: buyQty } : {}),
    ...(stockQty > 0
      ? {
          stock: {
            qty: stockQty,
            sources: cover.sources.map((s) => ({
              warehouse_id: s.warehouse_id,
              warehouse_code: s.warehouse_code,
              qty: s.qty,
            })),
          },
        }
      : {}),
    ...(usePo > 0 ? { po: usePo } : {}),
  };
}

/** The mixture in words: "Stock 31", "Buy 200", "Stock 10 + Buy 90", "Skipped". */
export function summariseMix(d: PlanDecision | undefined): string {
  if (!d) return 'Nothing';
  if (d.skip) return 'Skipped';
  const parts: string[] = [];
  if ((d.stock?.qty ?? 0) > 0) parts.push(`Stock ${fmtInt(d.stock!.qty)}`);
  if ((d.po ?? 0) > 0) parts.push(`PO ${fmtInt(d.po!)}`);
  if ((d.buy ?? 0) > 0) parts.push(`Buy ${fmtInt(d.buy!)}`);
  return parts.length ? parts.join(' + ') : 'Nothing';
}

export type PlanPillState = 'suggested' | 'unsaved' | 'saved' | 'confirmed' | 'skipped';

export interface PlanPillReading {
  state: PlanPillState;
  label: string;
  /** The mixture in words, beside the label. */
  mix: string;
}

/**
 * What the Decision cell says (plan 4.3): the status, and the mixture it applies to.
 *
 * Order matters. An unsaved edit outranks whatever is persisted, because that is the number
 * the buyer is looking at; a confirmed decision outranks a merely saved one; and a row nobody
 * has touched reads as the engine's suggestion rather than as nothing.
 */
export function planPillReading(
  edit: PlanRowEdit | undefined,
  decision: PlanDecision | undefined,
  suggested: PlanDecision,
): PlanPillReading {
  if (hasRowEdit(edit)) {
    const mix = edit?.decision ? summariseMix(edit.decision) : summariseMix(decision ?? suggested);
    return { state: 'unsaved', label: 'Unsaved', mix };
  }
  if (decision?.skip) return { state: 'skipped', label: 'Skipped', mix: 'Skipped' };
  if (decision) {
    return decision.confirmed
      ? { state: 'confirmed', label: 'Confirmed', mix: summariseMix(decision) }
      : { state: 'saved', label: 'Saved', mix: summariseMix(decision) };
  }
  return { state: 'suggested', label: 'Suggested', mix: summariseMix(suggested) };
}

/**
 * What is PERSISTED for a row.
 *
 * A grouped product row has no decision of its own - it is several recommendations, each
 * carrying the fanned-out copy - so its reading is the unanimous one across its members, and
 * `undefined` when they disagree (which is not the same as nobody having decided).
 */
export function decisionForLine(
  line: PlanLine,
  decisions: PlanDecisionMap,
): PlanDecision | undefined {
  if (!isGroupedLine(line)) return decisions[line.id];
  return groupDecisionState(line.__group.members.map((m) => m.id), decisions).decision;
}

/** Every recommendation id a row writes to: itself, or every member of a grouped row. */
export function recIdsForLine(line: PlanLine): string[] {
  return isGroupedLine(line) ? line.__group.members.map((m) => m.rec.id) : [line.rec.id];
}

/**
 * How many PRODUCTS carry an edit (R14).
 *
 * Counted by `product_id`, never by row or by recommendation: a product-grain row fans one
 * decision out to every location it summed, so counting recommendations made a product in
 * three bins read as three - the verified bug the ruling names. A row with no product id at
 * all (never seen on a real run) falls back to its own id so it is not silently dropped.
 */
export function editedProductCount(edits: PlanRowEditMap, lines: PlanLine[]): number {
  const products = new Set<string>();
  for (const line of lines) {
    if (!hasRowEdit(edits[line.id])) continue;
    products.add(line.product_id ?? line.id);
  }
  return products.size;
}

/**
 * What Confirm would send: how many PRODUCTS and how much cash.
 *
 * Every purchasable row with a BUY counts - edited, already saved, or untouched (R3: an
 * untouched row confirms as the engine's suggestion). Three kinds are left out, because
 * Confirm would draft nothing for them: a skipped row, a row whose mixture is all stock or
 * all open PO, and a row already confirmed into a draft purchase order that nobody has
 * edited since.
 *
 * `cash` is what the buys can be costed at; `unpriced` counts the ones that cannot be, and
 * they are never summed as zero - a line we cannot price still has to be bought, it simply
 * cannot be weighed against a budget.
 */
export interface ConfirmSummary {
  products: number;
  cash: number;
  unpriced: number;
}

export function confirmSummary(
  edits: PlanRowEditMap,
  decisions: PlanDecisionMap,
  lines: PlanLine[],
  coverFor?: (line: PlanLine) => CoverProposal,
  poFor?: (line: PlanLine) => PoReceipt[],
): ConfirmSummary {
  const products = new Set<string>();
  let cash = 0;
  let unpriced = 0;
  for (const line of lines) {
    if (!line.purchasable) continue;
    const edit = edits[line.id];
    const persisted = decisionForLine(line, decisions);
    // Already in a draft purchase order, and nothing new said about it. Confirming again
    // reconciles it to the same line, so counting it left the button live over a plan
    // with no work in it - "Confirm (2)" on two rows that both read Confirmed.
    if (!hasRowEdit(edit) && persisted?.confirmed) continue;
    const effective =
      edit?.decision ??
      persisted ??
      suggestedDecisionFor(line, coverFor?.(line) ?? NO_COVER, poFor?.(line) ?? []);
    if (effective.skip) continue;
    // Counted only where there is something to BUY. Confirm drafts purchase orders, and a
    // row covered entirely from stock or an open PO drafts nothing at all - so counting it
    // made the button read "Confirm (12)" and produce three lines, and left it live over a
    // plan where every remaining row was already covered.
    if ((effective.buy ?? 0) <= 0) continue;
    products.add(line.product_id ?? line.id);
    const cost = decidedCost(line, { buy: effective.buy });
    if (cost === null) unpriced += 1;
    else cash += cost;
  }
  return { products: products.size, cash, unpriced };
}
