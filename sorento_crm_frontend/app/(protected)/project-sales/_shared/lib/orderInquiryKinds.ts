/**
 * ONE vocabulary for what an order inquiry row still needs, used by the schedule matrix,
 * the list's "Linked to" column and the cards above both (PLAN-scm-cs-planning-uat.md
 * section 3.I2, AC-I11 to AC-I14).
 *
 * THREE KINDS, NOT SIX. The board's `supplyVocabulary` answers "where does this quantity
 * come from" across a whole ladder; purchasing's question is narrower and has exactly
 * three answers: the quantity is on an SPO already on its way, it is on a purchase order,
 * or nobody has put it on anything and it has to be bought.
 *
 * | Kind  | Label   | Colour  | What it is                                          |
 * | ----- | ------- | ------- | --------------------------------------------------- |
 * | `spo` | Use SPO | violet  | quantity linked to SPO allocations                  |
 * | `po`  | Use PO  | sky     | quantity linked to purchase order lines             |
 * | `buy` | Buy     | rose    | raised and unlinked - what still flows to planning  |
 *
 * The colours are the BOARD'S OWN tokens, taken from `supplyVocabulary` rather than
 * respelled: an SPO is the board's incoming supply and a purchase order is the same sky
 * a shared draw is, so a person who has read one screen reads the other without being
 * taught a second palette.
 *
 * A ROW IS THE UNIT AND IT IS NEVER SPLIT BETWEEN CELLS. A row linked 5 of 8 to a
 * purchase order carries BOTH `po` 5 and `buy` 3, which is what makes the bar a split
 * bar and the label read "PO 5 · Buy 3".
 *
 * Everything is derived from the row's own `links[]` - never from `linked_qty` beside
 * them - so the bar, the label and the cards cannot disagree with the documents the
 * "Linked to" column names.
 */
import { COLOURS } from './supplyVocabulary';
import { fromMinor, toMinor } from './supplyComposition';
import type {
  OrderInquiryKind,
  OrderInquiryKindTotals,
  OrderInquiryLink,
} from '../types/orderInquiry.types';

// Declared beside the wire it comes off, re-exported here because this file is what a
// screen imports when it needs the vocabulary.
export type { OrderInquiryKind };

/** What a person reads on a card. Three words each, and no others. */
export const KIND_LABELS: Record<OrderInquiryKind, string> = {
  spo: 'Use SPO',
  po: 'Use PO',
  buy: 'Buy',
};

/** The same three, short enough for a matrix cell: "PO 5 · Buy 3". */
export const KIND_SHORT_LABELS: Record<OrderInquiryKind, string> = {
  spo: 'SPO',
  po: 'PO',
  buy: 'Buy',
};

/** The board's own paint, not a second palette (see the file header). */
export const KIND_COLOURS: Record<OrderInquiryKind, { bar: string; text: string }> = {
  spo: COLOURS.incoming,
  po: COLOURS.shared,
  buy: COLOURS.buy,
};

/**
 * The fixed reading order: what is already on its way, what is on a document, what is
 * still to buy. A card keeps its place whether it reads 300 or 0, because a strip is
 * read by glancing at a position.
 */
export const KIND_ORDER: OrderInquiryKind[] = ['spo', 'po', 'buy'];

/** One kind's share of a row, a cell or a whole selection. */
export interface OrderInquiryKindSegment {
  kind: OrderInquiryKind;
  qty: string;
}

/**
 * The least a row has to carry to be read. Structural rather than
 * `OrderInquiryWorklistRow`, so the per-project rows and the worklist rows - which agree
 * about these three fields and about nothing else - are both readable here.
 */
export interface OrderInquiryKindRow {
  qty: string;
  links?: OrderInquiryLink[] | null;
  state?: string | null;
}

/**
 * Stored `cancelled`, and it owes nothing: no bar, no card, no filter (see below), and
 * no share of a schedule cell's own headline figure (`buildOrderInquiryMatrix`, which
 * imports this rather than respelling the word).
 */
export const CANCELLED_STATE = 'cancelled';

/**
 * The three totals over these rows, IN ORDER AND ALWAYS ALL THREE - what the cards are
 * drawn from, zeros included, so a card never moves the cards beside it.
 *
 * A CANCELLED ROW CONTRIBUTES NOTHING. Its quantity is not owed any more, so counting
 * its unlinked remainder as a Buy would tell purchasing to buy something somebody has
 * already called off; its links are history for the same reason and are already hidden
 * from the "Linked to" column by the one reader that serves it
 * (`ProjectOrderInquiryService.links_for_rows` filters them out). The summary's own
 * `kinds` facet drops them by the same rule, so the cards and the rows agree.
 */
export function kindTotals(rows: OrderInquiryKindRow[]): OrderInquiryKindSegment[] {
  const minor: Record<OrderInquiryKind, number> = { spo: 0, po: 0, buy: 0 };
  for (const row of rows) {
    if (row.state === CANCELLED_STATE) continue;
    let linked = 0;
    for (const link of row.links ?? []) {
      const qty = toMinor(link.qty);
      linked += qty;
      if (link.kind === 'spo') minor.spo += qty;
      else minor.po += qty;
    }
    // Never negative: a row linked beyond its own quantity is a data question, not a
    // negative segment somebody has to read backwards off a bar.
    minor.buy += Math.max(toMinor(row.qty) - linked, 0);
  }
  return KIND_ORDER.map((kind) => ({ kind, qty: fromMinor(minor[kind]) }));
}

/** The same, with the empty kinds dropped: what a BAR is drawn from. */
export function segmentsOfRows(rows: OrderInquiryKindRow[]): OrderInquiryKindSegment[] {
  return kindTotals(rows).filter((segment) => toMinor(segment.qty) !== 0);
}

/** One row's own split - "sky 5, rose 3" on a row linked 5 of 8 to a purchase order. */
export function segmentsOfRow(row: OrderInquiryKindRow): OrderInquiryKindSegment[] {
  return segmentsOfRows([row]);
}

/**
 * A composition in the fewest words that still name it: "Buy 3", "PO 8", "PO 5 · Buy 3".
 *
 * Every kind with a quantity, not just the largest one: a cell that is half bought and
 * half not is the cell somebody has to act on, and naming only its bigger half is how a
 * split row gets read as a settled one. Empty returns an empty string - the caller says
 * what nothing means on its own screen.
 */
export function kindText(segments: OrderInquiryKindSegment[]): string {
  return segments
    .map((segment) => `${KIND_SHORT_LABELS[segment.kind]} ${segment.qty}`)
    .join(' · ');
}

/**
 * Is every one of these rows wholly on a document? What draws the bar SOLID rather than
 * faded, the same rule the board's `SupplyBar` reads: solid means somebody has committed
 * the quantity, faded means part of it is still only an instruction.
 */
export function fullyLinked(rows: OrderInquiryKindRow[]): boolean {
  const totals = kindTotals(rows);
  return totals.every((segment) => segment.kind !== 'buy' || toMinor(segment.qty) === 0);
}

/**
 * The summary's `kinds` facet as segments, so the cards read the SERVER's totals through
 * the same shape `kindTotals` produces for a cell (AC-I11). Missing facet reads as three
 * zeros rather than as nothing: the cards keep their places while the answer is in
 * flight, and a zero card is disabled rather than gone.
 */
export function facetSegments(
  facet?: OrderInquiryKindTotals | null,
): OrderInquiryKindSegment[] {
  return KIND_ORDER.map((kind) => ({ kind, qty: facet?.[kind] ?? '0' }));
}
