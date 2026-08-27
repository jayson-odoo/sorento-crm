/**
 * S15: offset the buy suggestion against the outstanding PO book.
 *
 * > "if there is outstanding PO already then why should i buy ... I was expecting the
 * >  system to suggest me to use the PO quantity and don't need to order"
 *
 * The engine's NETTING never counts the PO book (incoming = SPO allocation, the standing
 * rule - the book is an AutoCount import that can be stale, and quietly netting it would
 * silently unbuy every row). The SUGGESTION counts it: the row says "Use PO 504" instead
 * of "Buy 200", and buying anyway stays one click away. Order of preference is the
 * buyer's own: use stock first, then what is arriving (already inside the net), then what
 * is ordered, and buy only the remainder.
 */
import type { PlanLine } from './planLine';
import { fmtTrimmedDecimal } from '../../lib/format';

/**
 * P8 (captain, 26 Aug 2026): "why does reorder planning consider outstanding PO again when
 * the OI already links to it".
 *
 * A PROJECT row's purchase order is consumed by the Order Inquiry - the raised row links to
 * the PO line and the row's Project figure drops by exactly that much - so offering the same
 * PO here as well is the same quantity twice and the buyer handles it twice. A RETAIL row
 * has no Order Inquiry at all, so the plan is the only place its demand and a purchase order
 * ever meet, and "Use PO" stays (QP2).
 *
 * ALL project is the test, not "any project": a cell carrying both channels has a retail
 * need that nothing else nets against a PO, and hiding the receipts there would leave that
 * half of the row buying what is already ordered. A grouped row is project-only when every
 * member it summed is.
 *
 * The backend serves the same rule (`po_book_service` skips a project-only cell), so this is
 * the second half of one decision rather than a rule of its own: the map arrives without the
 * project cells and this keeps a row from reading a member's key for them.
 */
export function isProjectOnlyLine(line: Pick<PlanLine, 'rec'>): boolean {
  const project = line.rec.project_committed ?? 0;
  const retail = line.rec.retail_committed ?? 0;
  return project > 0 && retail === 0;
}

export interface PoReceipt {
  po_number: string;
  status: string;
  expected_date: string | null;
  remaining: number;
}

/** How much of a remaining buy the PO book absorbs, and what is left to order. */
export function poOffset(buyQty: number, poQty: number): { usePo: number; buy: number } {
  const usePo = Math.min(Math.max(buyQty, 0), Math.max(poQty, 0));
  return { usePo, buy: Math.max(buyQty - usePo, 0) };
}

/** One line per order: the receipt the buyer verifies before trusting "don't order". */
export function describePoBook(receipts: PoReceipt[]): string[] {
  return receipts.map((r) => {
    const qty = fmtTrimmedDecimal(r.remaining, 2);
    const when = r.expected_date ? `expected ${r.expected_date}` : 'no promised date';
    return `${qty} still to come on ${r.po_number}, ${when}.`;
  });
}
