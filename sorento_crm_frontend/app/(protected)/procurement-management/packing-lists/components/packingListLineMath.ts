/**
 * The container workbook's own arithmetic (`consolidated_packing_list.py`'s `to_xlsx`),
 * read off the RMB sheet and reproduced here so the Shipment lines grid shows the exact
 * cells Download writes (AC-G2, AC-G6). Not imported from the backend - there is nothing to
 * import across languages - so a formula changed there has to be changed here too; the
 * fidelity test on the backend and the fixture test beside this file are what catch drift.
 *
 * `CTN QTY = F/G` when a pack size is stated, else the stored carton count; `CBM/CTN =
 * L*W*H/10^6`; the four totals multiply by CTN QTY (a blank ctn qty reads as the workbook's
 * own blank cell would in `=H*L` - zero, not "unknown"); `AMOUNT = PRICE*QTY`.
 */

/** A numeric column arrives as a string on the wire, or not at all; anything unreadable is
 *  "not stated" rather than 0 - a carton nobody measured and a carton of no size are
 *  different facts. */
export function toNum(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** A number as a person reads it: rounded to `dp` places, trailing zeros dropped. */
export function fmtDp(value: number | string | null | undefined, dp: number): string {
  const parsed = toNum(value);
  if (parsed === null) return '-';
  return String(Number(parsed.toFixed(dp)));
}

/** A measurement exactly as stated, no rounding - "-" when nobody stated one. */
export function fmtStated(value: number | string | null | undefined): string {
  const parsed = toNum(value);
  return parsed === null ? '-' : String(parsed);
}

export interface LineMeasurements {
  quantity_shipped: number | string | null | undefined;
  cartons_count?: number | string | null;
  pcs_per_carton?: number | string | null;
  carton_length_cm?: number | string | null;
  carton_width_cm?: number | string | null;
  carton_height_cm?: number | string | null;
  net_weight_per_carton?: number | string | null;
  /** Falls back to the single legacy weight column where the split one is blank - the same
   *  fallback the export and the read-only cell already apply. */
  gross_weight_per_carton?: number | string | null;
  weight_per_carton?: number | string | null;
  cbm?: number | string | null;
  unit_cost?: number | string | null;
}

export interface DerivedLineCells {
  ctnQty: number | null;
  cbmPerCtn: number | null;
  totalCbm: number | null;
  totalNw: number | null;
  totalGw: number | null;
  amount: number | null;
}

/** The six cells nobody types - worked out the same way the export works them out. */
export function deriveLineCells(line: LineMeasurements): DerivedLineCells {
  const qty = toNum(line.quantity_shipped) ?? 0;
  const pcs = toNum(line.pcs_per_carton);
  const cartonsStored = toNum(line.cartons_count);
  const ctnQty = pcs ? qty / pcs : cartonsStored || null;

  const length = toNum(line.carton_length_cm);
  const width = toNum(line.carton_width_cm);
  const height = toNum(line.carton_height_cm);
  const hasSize = length !== null && width !== null && height !== null;
  const cbmPerCtn = hasSize ? (length! * width! * height!) / 1_000_000 : null;
  // A carton whose size IS known but whose count is not still prints a total - the
  // workbook's own `=H*L` reads a blank H as 0, not as "skip this cell".
  const totalCbm = hasSize ? cbmPerCtn! * (ctnQty ?? 0) : toNum(line.cbm);

  const netWeight = toNum(line.net_weight_per_carton);
  const totalNw = netWeight !== null ? netWeight * (ctnQty ?? 0) : null;

  const grossWeight = toNum(line.gross_weight_per_carton) ?? toNum(line.weight_per_carton);
  const totalGw = grossWeight !== null ? grossWeight * (ctnQty ?? 0) : null;

  const price = toNum(line.unit_cost);
  const amount = price !== null ? price * qty : null;

  return { ctnQty, cbmPerCtn, totalCbm, totalNw, totalGw, amount };
}
