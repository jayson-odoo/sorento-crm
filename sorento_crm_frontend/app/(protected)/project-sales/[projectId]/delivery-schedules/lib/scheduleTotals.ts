/**
 * Decimal-safe quantity arithmetic and per-column reconciliation for the schedule grid.
 *
 * WHY NOT `Number(...)`: quantities arrive as strings because they are `Numeric` in Postgres
 * (contract section "Conventions"). Adding fifteen phase quantities with the float operator
 * introduces representation error the moment any of them carries a fraction, and this screen
 * exists to answer "do these two totals agree exactly". A comparison that is wrong once in a
 * thousand columns is worse than no comparison, because a reviewer stops checking. Everything
 * below is scaled-integer BigInt arithmetic on the string as given.
 */

interface Decimal {
  value: bigint;
  scale: number;
}

function parse(raw: string | null | undefined): Decimal | null {
  if (raw === null || raw === undefined) return null;
  // Thousand separators show up in transcribed documents ("1,826").
  const text = String(raw).trim().replace(/,/g, '');
  if (!text) return null;
  if (!/^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(text)) return null;
  const negative = text.startsWith('-');
  const unsigned = text.replace(/^[+-]/, '');
  const [int = '', frac = ''] = unsigned.split('.');
  const digits = `${int === '' ? '0' : int}${frac}`;
  const value = BigInt(digits);
  return { value: negative ? -value : value, scale: frac.length };
}

/** `10 ** n` as a bigint. Written out because BigInt literals need an ES2020 target. */
function pow10(n: number): bigint {
  return BigInt(`1${'0'.repeat(n)}`);
}

function align(a: Decimal, b: Decimal): [bigint, bigint] {
  const scale = Math.max(a.scale, b.scale);
  const lift = (d: Decimal) => d.value * pow10(scale - d.scale);
  return [lift(a), lift(b)];
}

function stringify(d: Decimal): string {
  const negative = d.value < BigInt(0);
  const digits = (negative ? -d.value : d.value).toString().padStart(d.scale + 1, '0');
  const cut = digits.length - d.scale;
  const int = digits.slice(0, cut);
  // Trailing zeros are noise on a quantity: the document says 72, not 72.00.
  const frac = digits.slice(cut).replace(/0+$/, '');
  return `${negative ? '-' : ''}${int}${frac ? `.${frac}` : ''}`;
}

/** True when the string is a quantity we can do arithmetic on. */
export function isQty(raw: string | null | undefined): boolean {
  return parse(raw) !== null;
}

/** Canonical form of one quantity, or null when it is not a number at all. */
export function normaliseQty(raw: string | null | undefined): string | null {
  const parsed = parse(raw);
  return parsed ? stringify(parsed) : null;
}

/** Sum, ignoring blanks. A blank cell is not a zero, it is an absence, and both add nothing. */
export function sumQty(values: (string | null | undefined)[]): string {
  let total: Decimal = { value: BigInt(0), scale: 0 };
  for (const raw of values) {
    const next = parse(raw);
    if (!next) continue;
    const [left, right] = align(total, next);
    total = { value: left + right, scale: Math.max(total.scale, next.scale) };
  }
  return stringify(total);
}

/** -1, 0 or 1. Returns null when either side is not a quantity. */
export function compareQty(
  a: string | null | undefined,
  b: string | null | undefined,
): number | null {
  const left = parse(a);
  const right = parse(b);
  if (!left || !right) return null;
  const [x, y] = align(left, right);
  if (x < y) return -1;
  if (x > y) return 1;
  return 0;
}

export function qtyEquals(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  return compareQty(a, b) === 0;
}

/** `a - b`, or null when either side is not a quantity. */
export function subtractQty(
  a: string | null | undefined,
  b: string | null | undefined,
): string | null {
  const left = parse(a);
  const right = parse(b);
  if (!left || !right) return null;
  const [x, y] = align(left, right);
  return stringify({ value: x - y, scale: Math.max(left.scale, right.scale) });
}

/** Signed difference for display: "+8" reads as an excess, "-8" as a shortfall. */
export function signedQty(value: string): string {
  return value.startsWith('-') ? value : `+${value}`;
}

// ------------------------------------------------------------------ columns

export type ColumnBlockerCode =
  | 'needs_product'
  | 'not_on_po'
  | 'po_mismatch'
  | 'reported_mismatch';

export interface ColumnBlocker {
  code: ColumnBlockerCode;
  /** A sentence, already carrying the numbers. Rendered as-is. */
  detail: string;
}

export interface ColumnState {
  /** Position in the version's `products` array. The API addresses columns by it. */
  index: number;
  /** Stable key for cell lookup: the product id when known, the position when not. */
  key: string;
  productId: string | null;
  productCode: string | null;
  productName: string | null;
  customerCode: string | null;
  /** True when a remembered customer code map identified this column by itself. */
  fromRememberedMap: boolean;
  /** Our sum of the cells currently on screen, edits included. */
  ourTotal: string;
  /** The schedule's own TOTAL QTY row, where the document has one. */
  reportedTotal: string | null;
  poQty: string | null;
  reconciled: boolean;
  blockers: ColumnBlocker[];
}

interface CellLike {
  phase_id: string;
  product_id: string | null;
  qty: string;
  product_index?: number | null;
}

interface ProductLike {
  product_id: string | null;
  product_code: string | null;
  product_name: string | null;
  customer_code_raw: string | null;
  resolution_source: 'map' | 'code' | 'manual' | null;
  reported_total: string | null;
  po_qty: string | null;
  product_index?: number | null;
}

interface PhaseLike {
  id: string;
}

/** The column a cell belongs to, mirroring `columnKey` below. */
function cellColumnKey(cell: CellLike): string {
  if (cell.product_id) return cell.product_id;
  if (cell.product_index !== null && cell.product_index !== undefined) {
    return `#${cell.product_index}`;
  }
  return '';
}

export function columnKey(product: ProductLike, index: number): string {
  if (product.product_id) return product.product_id;
  const declared = product.product_index;
  return `#${declared === null || declared === undefined ? index : declared}`;
}

export function columnIndex(product: ProductLike, index: number): number {
  const declared = product.product_index;
  return declared === null || declared === undefined ? index : declared;
}

/** `phaseId|columnKey` -> qty string. Blanks are absent from the map, never `"0"`. */
export type CellMap = Map<string, string>;

export function cellMapKey(phaseId: string, key: string): string {
  return `${phaseId}|${key}`;
}

export function buildCellMap(cells: CellLike[]): CellMap {
  const map: CellMap = new Map();
  for (const cell of cells) {
    const key = cellColumnKey(cell);
    if (!key) continue;
    map.set(cellMapKey(cell.phase_id, key), cell.qty);
  }
  return map;
}

/**
 * The three numbers per column and whether they agree.
 *
 * Mirrors the contract's rule exactly: reconciled when our total equals the PO quantity and,
 * where the document carries one, equals the schedule's own TOTAL QTY. `drafts` are the
 * reviewer's unsaved edits, applied over the stored cells so a correction flips the column
 * the instant it is typed rather than after a round trip.
 */
export function buildColumnStates(
  products: ProductLike[],
  phases: PhaseLike[],
  cells: CellLike[],
  drafts: Map<string, string> = new Map(),
): ColumnState[] {
  const stored = buildCellMap(cells);

  return products.map((product, index) => {
    const key = columnKey(product, index);
    const quantities = phases.map((phase) => {
      const mapKey = cellMapKey(phase.id, key);
      const draft = drafts.get(mapKey);
      return draft !== undefined ? draft : stored.get(mapKey);
    });
    const ourTotal = sumQty(quantities);
    const reportedTotal = normaliseQty(product.reported_total);
    const poQty = normaliseQty(product.po_qty);

    const blockers: ColumnBlocker[] = [];
    if (!product.product_id) {
      blockers.push({
        code: 'needs_product',
        detail: product.customer_code_raw
          ? `${product.customer_code_raw} is not matched to a product.`
          : 'This column is not matched to a product.',
      });
    }
    if (poQty === null) {
      blockers.push({
        code: 'not_on_po',
        detail: `Our total is ${ourTotal}. The PO version does not order this item.`,
      });
    } else if (!qtyEquals(ourTotal, poQty)) {
      const delta = subtractQty(ourTotal, poQty);
      blockers.push({
        code: 'po_mismatch',
        detail: `Our total is ${ourTotal}, the PO orders ${poQty}${
          delta ? ` (${signedQty(delta)})` : ''
        }.`,
      });
    }
    if (reportedTotal !== null && !qtyEquals(ourTotal, reportedTotal)) {
      const delta = subtractQty(ourTotal, reportedTotal);
      blockers.push({
        code: 'reported_mismatch',
        detail: `Our total is ${ourTotal}, the schedule's TOTAL QTY says ${reportedTotal}${
          delta ? ` (${signedQty(delta)})` : ''
        }.`,
      });
    }

    return {
      index: columnIndex(product, index),
      key,
      productId: product.product_id,
      productCode: product.product_code,
      productName: product.product_name,
      customerCode: product.customer_code_raw,
      fromRememberedMap: product.resolution_source === 'map',
      ourTotal,
      reportedTotal,
      poQty,
      reconciled: blockers.length === 0,
      blockers,
    };
  });
}

export interface PhaseGroup {
  area: string | null;
  phases: PhaseLike[];
}

/**
 * Phases in document order, grouped under their area heading.
 *
 * Order is by `(first appearance of the area, sequence)`. Sequence rather than label because
 * the COMMON AREA rows carry no label at all, so labels are not an identity (finding G6).
 */
export function groupPhasesByArea<T extends { area_group: string | null; sequence: number }>(
  phases: T[],
): { area: string | null; phases: T[] }[] {
  const groups: { area: string | null; phases: T[] }[] = [];
  const seen = new Map<string, number>();
  for (const phase of phases) {
    const areaKey = phase.area_group ?? '';
    let at = seen.get(areaKey);
    if (at === undefined) {
      at = groups.length;
      seen.set(areaKey, at);
      groups.push({ area: phase.area_group, phases: [] });
    }
    groups[at].phases.push(phase);
  }
  for (const group of groups) {
    group.phases.sort((a, b) => a.sequence - b.sequence);
  }
  return groups;
}

/** What a phase row is called when the document gave it no label (the COMMON AREA case). */
export function phaseRowLabel(phase: {
  label: string | null;
  sequence: number;
}): string {
  const label = phase.label?.trim();
  return label ? label : `Phase ${phase.sequence}`;
}
