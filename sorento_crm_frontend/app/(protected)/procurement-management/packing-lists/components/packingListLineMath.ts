import type {
  ConsolidatedPackingList,
  PackingListCompany,
} from '@/app/(protected)/scm/services/fulfilmentService';

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

export const SPLIT_COMPANIES: PackingListCompany[] = ['SORENTO', 'MOCHA'];

export interface CompanySplitRow {
  company: PackingListCompany;
  cbm: number;
  amount: number;
  /** Null where the container has not been costed yet - never 0, which would read as a
   *  clearance or freight that cost nothing rather than one nobody has priced. */
  clearance: number | null;
  insurance: number | null;
  chinaFreight: number | null;
}

export interface CompanySplitResult {
  rows: CompanySplitRow[];
  totalCbm: number;
  totalAmount: number;
  totalClearance: number | null;
  totalInsurance: number | null;
  totalChinaFreight: number | null;
}

/**
 * The per-company footer beneath the grid (AC-G4) - clearance and China freight follow the
 * CBM share, insurance follows the AMOUNT share, exactly as the export's footer formulas
 * apportion them (`consolidated_packing_list.py`'s `to_xlsx`, the SORENTO/MOCHA rows).
 *
 * `build()`'s own JSON already totals CBM per company (`split[]`); AMOUNT is not on that
 * total (`_totals` never summed a price), so it is summed here off the same lines the JSON
 * already carries - `qty * unit_cost` per line, the same formula the export's `U` column
 * writes.
 */
export function computeCompanySplit(data: ConsolidatedPackingList): CompanySplitResult {
  const amountByCompany = new Map<PackingListCompany, number>();
  for (const factory of data.factories ?? []) {
    for (const line of factory.lines ?? []) {
      const price = toNum(line.unit_cost);
      if (price === null) continue;
      const amount = price * line.qty;
      amountByCompany.set(line.company, (amountByCompany.get(line.company) ?? 0) + amount);
    }
  }
  const totalAmount = [...amountByCompany.values()].reduce((sum, v) => sum + v, 0);
  const totalCbm = data.total?.cbm ?? 0;

  const clearanceCost = toNum(data.costs?.clearance_cost);
  const chinaFreightCost = toNum(data.costs?.china_freight_cost);
  const insuranceRate = toNum(data.costs?.insurance_rate);

  const rows: CompanySplitRow[] = SPLIT_COMPANIES.map((company) => {
    const splitRow = (data.split ?? []).find((s) => s.company === company);
    const cbm = splitRow?.cbm ?? 0;
    const amount = amountByCompany.get(company) ?? 0;
    return {
      company,
      cbm,
      amount,
      clearance:
        clearanceCost !== null && totalCbm > 0 ? (cbm / totalCbm) * clearanceCost : null,
      chinaFreight:
        chinaFreightCost !== null && totalCbm > 0 ? (cbm / totalCbm) * chinaFreightCost : null,
      insurance:
        insuranceRate !== null && totalAmount > 0 ? (amount / totalAmount) * insuranceRate : null,
    };
  });

  const sumOrNull = (values: (number | null)[]): number | null => {
    const known = values.filter((v): v is number => v !== null);
    return known.length === 0 ? null : known.reduce((sum, v) => sum + v, 0);
  };

  return {
    rows,
    totalCbm,
    totalAmount,
    totalClearance: sumOrNull(rows.map((r) => r.clearance)),
    totalInsurance: sumOrNull(rows.map((r) => r.insurance)),
    totalChinaFreight: sumOrNull(rows.map((r) => r.chinaFreight)),
  };
}
