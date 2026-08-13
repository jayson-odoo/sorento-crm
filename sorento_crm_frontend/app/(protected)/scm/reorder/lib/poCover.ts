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
    const qty = Number.isInteger(r.remaining) ? String(r.remaining) : r.remaining.toFixed(2);
    const when = r.expected_date ? `expected ${r.expected_date}` : 'no promised date';
    return `${qty} still to come on ${r.po_number}, ${when}.`;
  });
}
