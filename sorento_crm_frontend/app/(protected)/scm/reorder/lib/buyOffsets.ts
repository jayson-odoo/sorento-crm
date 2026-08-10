/**
 * The buy quantity is a PROPOSAL, and every thing that reduced it is a SUGGESTION.
 *
 * > "i want to keep the using 1 on hand quantity from the warehouse a suggestion instead of
 * >  a decision by us, cause yes I need 24, and 1 on hand, but, we should suggest to use the
 * >  1 on hand, not to decide use 1 on hand and buy 23"
 *
 * The engine nets on-hand, incoming SPO and outstanding PO into one number and shows only
 * the result. Each of those is really a claim - that the unit on the shelf is usable, that
 * the container will land, that the supplier will deliver - and each can be wrong. A unit on
 * hand may be a display piece, damaged, or held for somebody. An outstanding PO may be one
 * the buyer has stopped believing in. When the engine applies those claims silently, the
 * buyer cannot disagree with them; they can only retype the total and lose the reasoning.
 *
 * So the arithmetic is inverted for display: start from what is needed, list what we propose
 * to cover it with, and let each line be declined.
 *
 * ## Why declining simply adds the offset back
 *
 * Every basis the engine supports computes `buy = target - net`, where
 * `net = on_hand + incoming + on_order - committed`. The bases differ only in `target`
 * (an order-up-to level, or a stored reorder level). Declining an offset means recomputing
 * with that term removed from `net`:
 *
 *     net'  = net - offset
 *     buy'  = target - net' = (target - net) + offset = buy + offset
 *
 * So the target never has to be re-derived and this stays correct on both bases, including
 * the pooled case where `target` belongs to the pool rather than the bin. Rounding is then
 * re-applied, because MoQ and the order multiple are supplier terms that hold whatever the
 * buyer decides.
 */
import type { M8PlanRow } from './planRow';

export type BuyOffsetKey = 'on_hand' | 'incoming_spo' | 'outstanding_po';

export interface BuyOffset {
  key: BuyOffsetKey;
  /** What the buyer is being asked to agree to, in their words. */
  label: string;
  /** Units this offset removes from the buy. Always > 0 - a zero offset is not a choice. */
  qty: number;
  /** Why declining it is a real thing to do, shown when the row is open. */
  hint: string;
}

/**
 * The offsets actually available on a row, largest first.
 *
 * An offset of zero is left out rather than listed as an unchecked line: "incoming SPO 0" is
 * not a suggestion the buyer can accept or decline, it is the absence of one, and a list of
 * empty choices buries the one real choice.
 */
export function buyOffsetsFor(row: M8PlanRow): BuyOffset[] {
  const rec = row.rec;
  const where = rec.warehouse_code ?? rec.warehouse_name ?? null;
  const out: BuyOffset[] = [];
  const push = (key: BuyOffsetKey, qty: number | null | undefined, label: string, hint: string) => {
    const n = Number(qty ?? 0);
    if (Number.isFinite(n) && n > 0) out.push({ key, qty: n, label, hint });
  };
  push(
    'on_hand',
    rec.on_hand,
    where ? `Use what is on hand at ${where}` : 'Use what is on hand',
    'Decline if the stock is a display piece, damaged, or held for somebody.',
  );
  push(
    'incoming_spo',
    rec.incoming_spo,
    'Count the incoming shipment',
    'Decline if the shipment is late, short, or you would rather not wait for it.',
  );
  push(
    'outstanding_po',
    rec.outstanding_po,
    'Count the outstanding purchase order',
    'Decline if you no longer expect the supplier to deliver it.',
  );
  return out.sort((a, b) => b.qty - a.qty);
}

/** What the row needs before any offset is applied. */
export function grossRequirement(row: M8PlanRow): number {
  return row.order_qty + buyOffsetsFor(row).reduce((t, o) => t + o.qty, 0);
}

/**
 * Round a quantity the way the engine does: never below MoQ, then up to a whole multiple.
 *
 * A quantity of zero stays zero - "nothing to buy" must not be rounded up into a purchase by
 * a minimum that only applies once you have decided to order at all.
 */
export function roundToSupplierTerms(qty: number, row: M8PlanRow): number {
  if (qty <= 0) return 0;
  const moq = Number(row.order_qty_inputs.moq ?? 0) || 0;
  const multiple = Number(row.order_qty_inputs.order_multiple ?? 0) || 0;
  let out = Math.max(qty, moq);
  if (multiple > 1) out = Math.ceil(out / multiple) * multiple;
  return out;
}

/** The buy quantity once `declined` offsets are added back and the terms re-applied. */
export function qtyWithDeclined(row: M8PlanRow, declined: ReadonlySet<BuyOffsetKey>): number {
  const addBack = buyOffsetsFor(row)
    .filter((o) => declined.has(o.key))
    .reduce((t, o) => t + o.qty, 0);
  return roundToSupplierTerms(row.order_qty + addBack, row);
}

/**
 * The reason written onto the adjustment, so the decision survives the run.
 *
 * Phrased as what the buyer decided, not as what the number became: "Not using the 1 on hand
 * at BRW" is reviewable six weeks later; "qty 23 to 24" is not.
 */
export function declineReason(row: M8PlanRow, declined: ReadonlySet<BuyOffsetKey>): string {
  const parts = buyOffsetsFor(row)
    .filter((o) => declined.has(o.key))
    .map((o) => {
      if (o.key === 'on_hand') {
        const where = row.rec.warehouse_code ?? row.rec.warehouse_name;
        return `the ${o.qty} on hand${where ? ` at ${where}` : ''}`;
      }
      if (o.key === 'incoming_spo') return `the ${o.qty} incoming`;
      return `the ${o.qty} on outstanding PO`;
    });
  if (!parts.length) return '';
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(', ')} or ${parts[parts.length - 1]}`;
  return `Not counting ${list} towards this requirement.`;
}
