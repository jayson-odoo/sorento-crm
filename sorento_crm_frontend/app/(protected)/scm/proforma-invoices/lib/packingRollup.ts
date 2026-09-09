/**
 * The one derivation the Lines tab makes from the packing rows it already holds (AC-B11).
 *
 * Not a service call and not a second fetch: the rows travel on the invoice detail payload
 * the page has, and "packed" is a sum over the rows of one line. The roll-up onto the LINE
 * itself (cartons, CBM, weights) is the server's own (`_rollup_packing`), read straight off
 * the line - it is not recomputed here.
 */
import type { ProformaInvoicePackingLine } from '../types/packingLine.types';

/** Packed quantity for a line (AC-B11): sum of MATCHED rows' qty, or null with no rows at
 *  all (the Lines tab shows "-" rather than 0, which would read as "packed nothing"). */
export function packedQtyForLine(lineId: string, rows: ProformaInvoicePackingLine[]): number | null {
  const forLine = rows.filter(
    (r) => r.proforma_invoice_line_id === lineId && r.match_state !== 'dismissed',
  );
  if (!forLine.length) return null;
  return forLine.reduce((sum, r) => sum + (r.qty ?? 0), 0);
}
