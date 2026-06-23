/** Pure helpers for portal submission line items (purchase request / sponsorship).
 *
 * Extracted from SubmissionForm so the total-persistence + filter rules are unit
 * testable without rendering the (heavy, radix-laden) form in jsdom. */

export interface RawProductLine {
  item_code?: string;
  quantity?: string;
  unit_price?: string;
  total?: string;
  remark?: string;
}

export interface CleanedProductLine {
  // Index signature so the result is assignable to the portal-client payload
  // type (Record<string, unknown>[]) while keeping named fields for tests.
  [key: string]: string | null;
  item_code: string | null;
  quantity: string | null;
  unit_price: string | null;
  total: string | null;
  remark: string | null;
}

/** Compute a line total (qty × unit price) as a string, or '' when either side
 *  is not a finite number. Mirrors the display fallback so the persisted total
 *  matches what the user sees in the Total box. */
export function computeLineTotal(quantity?: string, unitPrice?: string): string {
  const q = Number(quantity);
  const u = Number(unitPrice);
  if (
    (quantity ?? '').trim() === '' ||
    (unitPrice ?? '').trim() === '' ||
    !Number.isFinite(q) ||
    !Number.isFinite(u)
  ) {
    return '';
  }
  return (q * u).toFixed(2);
}

/** Trim + normalize raw line rows into the payload shape sent to the backend.
 *  - Persists the computed total when the Total box is empty (the box only ever
 *    showed it as a display fallback).
 *  - Keeps any line with content: identifier, quantity, remark, OR pricing
 *    (a priced line with no item code / qty must still survive). */
export function cleanLineItems(products: RawProductLine[]): CleanedProductLine[] {
  return products
    .map((p) => {
      const quantity = (p.quantity ?? '').trim() || null;
      const unit_price = (p.unit_price ?? '').trim() || null;
      const total =
        (p.total ?? '').trim() || computeLineTotal(p.quantity, p.unit_price) || null;
      return {
        item_code: (p.item_code ?? '').trim() || null,
        quantity,
        unit_price,
        total,
        remark: (p.remark ?? '').trim() || null,
      };
    })
    .filter((p) => p.item_code || p.quantity || p.remark || p.unit_price || p.total);
}
