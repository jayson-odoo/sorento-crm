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
  | 'reported_mismatch'
  /**
   * The backend refused this column for a reason this file does not derive.
   *
   * A safety net, not a normal outcome: the rules below mirror the server's `_verdict`, so
   * this only fires if the two ever drift. Being laxer than the server is the bad direction
   * - the screen would invite a confirm the server then rejects.
   */
  | 'server';

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
  /**
   * A person overruled the blockers below as a false signal. They are still computed and
   * still shown, because the check was not withdrawn; the column just stops blocking.
   */
  dismissed: boolean;
  dismissedReason: string | null;
  dismissedByName: string | null;
  /**
   * Something worth saying about a column that still reconciles, and never blocks it.
   *
   * A shortfall against the PO is the main one: a partial schedule is the normal state of a
   * live project. Computed here so it tracks what is being typed, and taken from the server's
   * own `warning` on a column nobody has edited.
   */
  warning: string | null;
}

/**
 * The size of a disagreement in words: ", 18 short" or ", 18 over".
 *
 * "(-18)" is a sign a reader has to decode, and half of them decode it backwards. Empty
 * when the difference cannot be computed, so the sentence around it still reads.
 */
function describeGap(delta: string | null): string {
  if (delta === null) return '';
  const short = delta.startsWith('-');
  const size = short ? delta.slice(1) : delta;
  if (size === '0') return '';
  return `, ${size} ${short ? 'short' : 'over'}`;
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
  dismissed?: boolean;
  dismissed_reason?: string | null;
  dismissed_by_name?: string | null;
  warning?: string | null;
  /** The server's own verdict, used only as a backstop to the rules computed here. */
  reconciled?: boolean;
  reason?: string | null;
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
 * The three numbers per column, and whether they agree.
 *
 * Mirrors the server's `_verdict` rule for rule, because the two verdicts appear side by side
 * and the screen must never ask for work the server would not: what BLOCKS is an unmatched
 * product, a column with no PO quantity to check against, a column asking for MORE than the
 * PO ordered, or phases that do not add up to the sheet's own TOTAL QTY row. Asking for LESS
 * is a partial schedule, which is normal, and reads as a warning.
 *
 * `drafts` are the reviewer's unsaved edits, applied over the stored cells so a correction
 * flips the column the instant it is typed rather than after a round trip.
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

    /**
     * Every sentence names the fact AND the next action.
     *
     * "Our total is 240, the PO orders 258 (-18)." states what is and leaves the reviewer
     * to work out what to do about it, which is the question they asked out loud the first
     * time they saw this screen. The numbers are the same numbers; what follows them is
     * what to click next.
     */
    const blockers: ColumnBlocker[] = [];
    if (!product.product_id) {
      blockers.push({
        code: 'needs_product',
        detail: product.customer_code_raw
          ? `${product.customer_code_raw} is not matched to a product. Pick the product this column means.`
          : 'This column is not matched to a product. Pick the product it means.',
      });
    }
    if (poQty === null) {
      blockers.push({
        code: 'not_on_po',
        detail:
          `The PO version does not order this item, but the schedule asks for ${ourTotal}. ` +
          'Check the column is the right product, or amend the PO.',
      });
    }
    /**
     * A SHORTFALL is a WARNING, not a blocker, and this is the same rule as the server's
     * `_verdict` (captain, 2026-08-18).
     *
     * A delivery schedule is routinely PARTIAL: the customer schedules part of what they
     * ordered now and the rest on a later document, so "asks for 195 of the 200 ordered" is
     * the normal state of a live project. Blocking on it made the screen demand a correction
     * to something that was never wrong - and worse, disagree with the backend, which would
     * confirm the same schedule happily.
     *
     * Asking for MORE than was ordered still blocks: the schedule cannot commit quantity
     * nobody bought.
     */
    let shortfall: string | null = null;
    if (poQty !== null && !qtyEquals(ourTotal, poQty)) {
      const delta = subtractQty(ourTotal, poQty);
      if (delta !== null && delta.startsWith('-')) {
        shortfall =
          `The schedule asks for ${ourTotal} of the ${poQty} on the purchase order; ` +
          `the remaining ${delta.slice(1)} is expected on a later schedule.`;
      } else {
        const gap = describeGap(delta);
        blockers.push({
          code: 'po_mismatch',
          detail:
            `The schedule asks for ${ourTotal} and the PO orders ${poQty}${gap}. ` +
            'Correct a phase quantity, or amend the PO.',
        });
      }
    }
    if (reportedTotal !== null && !qtyEquals(ourTotal, reportedTotal)) {
      blockers.push({
        code: 'reported_mismatch',
        detail:
          `The phases add up to ${ourTotal} but the schedule's own TOTAL QTY row says ` +
          `${reportedTotal}. One of the two was misread, so check the cells against the paper.`,
      });
    }

    const dismissed = product.dismissed === true;

    /**
     * Whether the reviewer has this column part-typed.
     *
     * It decides who gets the last word. The sentences here are recomputed on every
     * keystroke, so while a column is being edited only they can be right; the server's
     * `warning` and `reason` describe the numbers as they were SAVED and would contradict
     * what is on screen. Untouched, the server's wording is the better of two identical
     * facts and leads.
     */
    const edited = phases.some((phase) => drafts.has(cellMapKey(phase.id, key)));

    /**
     * The backstop: never be laxer than the server. A refusal we cannot derive is still a
     * refusal, and it is shown as what the server said it was.
     *
     * Except over a shortfall, and that exception is load-bearing. Verdicts are STORED with
     * the version, so a schedule read before a shortfall became a warning still carries the
     * old refusal ("the column adds up to 53, the purchase order says 1777") until something
     * recomputes it. Trusting that would put the blocker straight back and undo the rule this
     * file was just changed to match - measured on the live stack, all 21 blocked columns of
     * HQ/26/01/121 came back that way. Where we have derived the shortfall ourselves, our
     * verdict is the current one and it wins.
     */
    if (
      blockers.length === 0 &&
      shortfall === null &&
      !edited &&
      product.reconciled === false &&
      !dismissed &&
      product.reason
    ) {
      blockers.push({ code: 'server', detail: product.reason });
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
      // A dismissed column counts as reconciled, which is the whole point of dismissing it:
      // it stops being work to do and stops holding up the confirm. `blockers` is left
      // populated so the screen can still say what the check found.
      reconciled: blockers.length === 0 || dismissed,
      blockers,
      dismissed,
      dismissedReason: product.dismissed_reason ?? null,
      dismissedByName: product.dismissed_by_name ?? null,
      warning: shortfall ?? (edited ? null : (product.warning ?? null)),
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
