/**
 * The one derivation the Lines tab makes from the packing rows it already holds (AC-B11).
 *
 * Not a service call and not a second fetch: the rows travel on the invoice detail payload
 * the page has, and "packed" is a sum over the rows of one line. The roll-up onto the LINE
 * itself (cartons, CBM, weights) is the server's own (`_rollup_packing`), read straight off
 * the line - it is not recomputed here.
 */
import type { ProformaInvoicePackingLine } from '../types/packingLine.types';

/** Packed quantity for a line (AC-B11): the sum of its rows' qty, DISMISSED rows excluded -
 *  a dismissed row is the operator saying the invoice does not price it, so counting it
 *  would make the line read as over-packed. Null when the line has no rows at all, so the
 *  Lines tab shows "-" rather than a 0 that reads as "packed nothing". */
export function packedQtyForLine(lineId: string, rows: ProformaInvoicePackingLine[]): number | null {
  const forLine = rows.filter(
    (r) => r.proforma_invoice_line_id === lineId && r.match_state !== 'dismissed',
  );
  if (!forLine.length) return null;
  return forLine.reduce((sum, r) => sum + (r.qty ?? 0), 0);
}
