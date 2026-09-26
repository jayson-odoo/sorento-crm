/**
 * S15: the outstanding PO book, as the row's receipts read it.
 *
 * > "if there is outstanding PO already then why should i buy ... I was expecting the
 * >  system to suggest me to use the PO quantity and don't need to order"
 *
 * Since #828 the ENGINE nets the open PO book into the same `net` the row is sized
 * against, so the suggestion's "PO 339" part is a DISPLAY of what that net already
 * consumed rather than a second offset applied on top of it (PLAN-reorder-one-formula.md).
 * What survives here is the receipt list itself: which orders the figure stands for, so a
 * buyer can check them before trusting "do not order".
 */
import { fmtTrimmedDecimal } from '../../lib/format';

// P8 (`isProjectOnlyLine`, the captain's "why does reorder planning consider outstanding
// PO again when the OI already links to it") is RETIRED (PLAN-reorder-one-formula.md,
// 11 Sep 2026): the engine nets every row's open PO ONCE, project demand included since
// #828, so hiding a project-only row's own PO part broke the Suggestion's own identity
// (Stock + PO + Buy = need) for exactly that row. The backend serves the same fix
// (`po_book_service` no longer drops a project-only cell).

export interface PoReceipt {
  po_number: string;
  status: string;
  expected_date: string | null;
  remaining: number;
}

// `poOffset` is DELETED (PLAN-reorder-one-formula.md, 11 Sep 2026). It nets a PO against a
// remaining buy, and since #828 the engine's `recommended_qty` is already net of the open PO
// book - so every caller was subtracting the same units twice. `orderQtyLedger.composeMixture`
// now clamps every part against the NEED instead, which is the one place that netting happens.

/** One line per order: the receipt the buyer verifies before trusting "don't order". */
export function describePoBook(receipts: PoReceipt[]): string[] {
  return receipts.map((r) => {
    const qty = fmtTrimmedDecimal(r.remaining, 2);
    const when = r.expected_date ? `expected ${r.expected_date}` : 'no promised date';
    return `${qty} still to come on ${r.po_number}, ${when}.`;
  });
}
