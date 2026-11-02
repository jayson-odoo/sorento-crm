/**
 * Quotation grid scopes (PS-QUOTE-MATRIX): column headers over column shoulders, a quantity per
 * cell. Pure functions only, shared by the Lines grid (cells, pairs, footer, paste), the header
 * editor (add, rename, move, remove) and the tests.
 *
 * The backend computes the same numbers in `app/services/quotation_matrix.py` (`matrix_summary`)
 * for the PDF and the Excel file; the rules are the card's R5-R10:
 * - a line's quantity is the sum of its cells (blank = 0);
 * - a header gets a Qty / RM pair on the row only when the scope has 2+ headers and that header
 *   has 2+ columns (anything less would repeat the row total);
 * - a rate-only line prints its cells and adds to no total.
 *
 * Quantities and money stay decimal STRINGS (`money.ts`), never floats.
 */
import { compareMoney, isDecimalString, multiplyMoney, sumMoney } from './money';

export interface MatrixCol {
  key: string;
  label: string;
}

/** One column header. With no `cols` it is one quantity column under its own label. */
export interface MatrixHeader {
  key: string;
  label: string;
  cols: MatrixCol[];
}

/** `{leaf key: quantity}`: what a line holds per quantity column. */
export type MatrixCells = Record<string, string>;

/** One quantity column, in display order, with the header it sits under. */
export interface MatrixLeaf {
  key: string;
  label: string;
  headerKey: string;
  headerLabel: string;
  /** True for a header with no columns: the leaf IS the header. */
  isHeader: boolean;
}

export const KEY_PATTERN = /^[a-z0-9][a-z0-9_-]{0,39}$/;
export const MAX_LABEL = 60;
const MAX_QTY = '9999999.99';

/** Null or `[]` both mean "no columns": today's single Qty column. */
export function hasColumns(headers: MatrixHeader[] | null | undefined): headers is MatrixHeader[] {
  return Array.isArray(headers) && headers.length > 0;
}

/** The quantity columns in order: each header's columns, or the header itself when it has none. */
export function leaves(headers: MatrixHeader[] | null | undefined): MatrixLeaf[] {
  if (!hasColumns(headers)) return [];
  return headers.flatMap((header): MatrixLeaf[] =>
    header.cols.length === 0
      ? [
          {
            key: header.key,
            label: header.label,
            headerKey: header.key,
            headerLabel: header.label,
            isHeader: true,
          },
        ]
      : header.cols.map((col) => ({
          key: col.key,
          label: col.label,
          headerKey: header.key,
          headerLabel: header.label,
          isHeader: false,
        })),
  );
}

export function leafKeys(headers: MatrixHeader[] | null | undefined): string[] {
  return leaves(headers).map((leaf) => leaf.key);
}

/** "<header> / <col>", or the header alone for a one-column header. */
export function leafLabel(leaf: MatrixLeaf): string {
  return leaf.isHeader ? leaf.headerLabel : `${leaf.headerLabel} / ${leaf.label}`;
}

/** Every key a version already uses, headers and columns alike (they share one namespace). */
export function usedKeys(headers: MatrixHeader[] | null | undefined): Set<string> {
  const keys = new Set<string>();
  (headers ?? []).forEach((header) => {
    keys.add(header.key);
    header.cols.forEach((col) => keys.add(col.key));
  });
  return keys;
}

/**
 * A generated key, never derived from the label (R13: a rename keeps the cells). Matches the
 * backend's `^[a-z0-9][a-z0-9_-]{0,39}$` and is unique against `taken`.
 */
export function newKey(taken: Iterable<string> = []): string {
  const used = new Set(taken);
  for (;;) {
    const key = `c${Math.random().toString(36).slice(2, 10)}`;
    if (KEY_PATTERN.test(key) && !used.has(key)) return key;
  }
}

/** A cell value that counts: a non-negative decimal. Anything else is blank (0). */
function counted(value: string | null | undefined): string | null {
  const text = (value ?? '').trim();
  if (text === '' || !isDecimalString(text)) return null;
  return compareMoney(text, '0') === -1 ? null : text;
}

/** The sum of the given cells (all of them when `keys` is omitted), to two decimals. */
export function sumCells(cells: MatrixCells | null | undefined, keys?: string[]): string {
  const source = cells ?? {};
  const values = (keys ?? Object.keys(source))
    .map((key) => counted(source[key]))
    .filter((value): value is string => value !== null);
  return sumMoney(values) ?? '0.00';
}

/** True when any of the given cells holds a quantity (a pair with none prints `-`, R9). */
export function anyCell(cells: MatrixCells | null | undefined, keys: string[]): boolean {
  return keys.some((key) => counted(cells?.[key]) !== null);
}

/** R7: a Qty / RM pair after this header, when the scope has 2+ headers and it has 2+ columns. */
export function hasPair(headers: MatrixHeader[] | null | undefined, index: number): boolean {
  if (!hasColumns(headers) || headers.length < 2) return false;
  return (headers[index]?.cols.length ?? 0) >= 2;
}

/** What `summary` reads off a line. */
export interface MatrixLineInput {
  qty_cells: MatrixCells | null | undefined;
  unit_price: string | null | undefined;
  is_rate_only?: boolean;
}

export interface MatrixPair {
  qty: string;
  amount: string;
  /** Every cell under the header is blank: prints `-` / `-`. */
  blank: boolean;
}

export interface MatrixRowSummary {
  pairs: Record<string, MatrixPair>;
  totalQty: string;
  /** 0 for a rate-only line. */
  amount: string;
}

export interface MatrixFooter {
  leafQty: Record<string, string>;
  pairQty: Record<string, string>;
  pairAmount: Record<string, string>;
  totalQty: string;
  amount: string;
}

export interface MatrixSummary {
  rows: MatrixRowSummary[];
  footer: MatrixFooter;
}

function amountOf(qty: string, price: string | null | undefined, rateOnly: boolean): string {
  if (rateOnly) return '0.00';
  return multiplyMoney(qty, (price ?? '').trim() || '0') ?? '0.00';
}

/**
 * Per-row pairs and totals, and the footer per leaf, per pair and overall. A rate-only line keeps
 * its own row figures (it prints its cells) and adds to no footer total (R10).
 */
export function summary(headers: MatrixHeader[], lines: MatrixLineInput[]): MatrixSummary {
  const allLeaves = leafKeys(headers);
  const pairHeaders = headers.filter((_, index) => hasPair(headers, index));

  const rows = lines.map((line) => {
    const rateOnly = Boolean(line.is_rate_only);
    const pairs: Record<string, MatrixPair> = {};
    pairHeaders.forEach((header) => {
      const keys = header.cols.map((col) => col.key);
      const qty = sumCells(line.qty_cells, keys);
      pairs[header.key] = {
        qty,
        amount: amountOf(qty, line.unit_price, rateOnly),
        blank: !anyCell(line.qty_cells, keys),
      };
    });
    const totalQty = sumCells(line.qty_cells, allLeaves);
    return { pairs, totalQty, amount: amountOf(totalQty, line.unit_price, rateOnly) };
  });

  const counting = lines
    .map((line, index) => ({ line, row: rows[index] }))
    .filter(({ line }) => !line.is_rate_only);
  const sum = (values: string[]) => sumMoney(values) ?? '0.00';

  const leafQty: Record<string, string> = {};
  allLeaves.forEach((key) => {
    leafQty[key] = sum(counting.map(({ line }) => sumCells(line.qty_cells, [key])));
  });
  const pairQty: Record<string, string> = {};
  const pairAmount: Record<string, string> = {};
  pairHeaders.forEach((header) => {
    pairQty[header.key] = sum(counting.map(({ row }) => row.pairs[header.key].qty));
    pairAmount[header.key] = sum(counting.map(({ row }) => row.pairs[header.key].amount));
  });

  return {
    rows,
    footer: {
      leafQty,
      pairQty,
      pairAmount,
      totalQty: sum(counting.map(({ row }) => row.totalQty)),
      amount: sum(counting.map(({ row }) => row.amount)),
    },
  };
}

// ----------------------------------------------------------------------------- paste

export interface PastedCell {
  rowIndex: number;
  leafIndex: number;
  /** '' for a blank or `-` cell. */
  value: string;
}

export type PasteResult = { ok: true; cells: PastedCell[] } | { ok: false; error: string };

/** "1,250" as Excel copies a formatted number, to "1250". */
function pastedNumber(raw: string): string | null {
  const text = raw.trim().replace(/,/g, '');
  if (text === '' || text === '-') return '';
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  return compareMoney(text, MAX_QTY) === 1 ? null : text;
}

/**
 * A block copied from a spreadsheet (tabs between cells, newlines between rows), placed from the
 * cell it is pasted into, right and down (R14). `-` and blanks paste as blank; a non-number
 * refuses the WHOLE paste, naming the first bad cell. Clipping to the grid is the caller's: paste
 * never creates rows or columns.
 */
export function parsePaste(text: string, startLeafIndex: number, startRowIndex: number): PasteResult {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  // A spreadsheet copy ends with a newline; that last empty line is not a row.
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();
  const cells: PastedCell[] = [];
  for (let r = 0; r < lines.length; r += 1) {
    const parts = lines[r].split('\t');
    for (let c = 0; c < parts.length; c += 1) {
      const value = pastedNumber(parts[c]);
      if (value === null) {
        return {
          ok: false,
          error: `Nothing pasted: "${parts[c].trim()}" (row ${r + 1}, column ${c + 1} of the copied block) is not a quantity.`,
        };
      }
      cells.push({ rowIndex: startRowIndex + r, leafIndex: startLeafIndex + c, value });
    }
  }
  return { ok: true, cells };
}

// --------------------------------------------------------------------- header edits

function cleanLabel(label: string): string {
  return label.trim().slice(0, MAX_LABEL);
}

export function addHeader(headers: MatrixHeader[], label: string): MatrixHeader[] {
  return [...headers, { key: newKey(usedKeys(headers)), label: cleanLabel(label), cols: [] }];
}

export function addCol(headers: MatrixHeader[], headerKey: string, label: string): MatrixHeader[] {
  const key = newKey(usedKeys(headers));
  return headers.map((header) =>
    header.key === headerKey
      ? { ...header, cols: [...header.cols, { key, label: cleanLabel(label) }] }
      : header,
  );
}

/** Renames a header or a column, whichever owns `key`. A blank label is refused (unchanged). */
export function renameKey(headers: MatrixHeader[], key: string, label: string): MatrixHeader[] {
  const next = cleanLabel(label);
  if (!next) return headers;
  return headers.map((header) =>
    header.key === key
      ? { ...header, label: next }
      : {
          ...header,
          cols: header.cols.map((col) => (col.key === key ? { ...col, label: next } : col)),
        },
  );
}

/** Removes a header (with its columns) or a column, whichever owns `key`. */
export function removeKey(headers: MatrixHeader[], key: string): MatrixHeader[] {
  return headers
    .filter((header) => header.key !== key)
    .map((header) => ({ ...header, cols: header.cols.filter((col) => col.key !== key) }));
}

function move<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function moveHeader(headers: MatrixHeader[], fromKey: string, toKey: string): MatrixHeader[] {
  return move(
    headers,
    headers.findIndex((header) => header.key === fromKey),
    headers.findIndex((header) => header.key === toKey),
  );
}

/** Reorders within one header only: a column never changes header by a drag. */
export function moveCol(headers: MatrixHeader[], fromKey: string, toKey: string): MatrixHeader[] {
  return headers.map((header) => {
    const from = header.cols.findIndex((col) => col.key === fromKey);
    const to = header.cols.findIndex((col) => col.key === toKey);
    return from >= 0 && to >= 0 ? { ...header, cols: move(header.cols, from, to) } : header;
  });
}

/**
 * Copy columns from another scope (R11): its headers and columns, never its quantities, appended
 * after any this scope already has. Fresh keys, so nothing is matched against the source's cells.
 */
export function appendCopy(target: MatrixHeader[], source: MatrixHeader[]): MatrixHeader[] {
  const taken = usedKeys(target);
  const fresh = () => {
    const key = newKey(taken);
    taken.add(key);
    return key;
  };
  return [
    ...target,
    ...source.map((header) => ({
      key: fresh(),
      label: header.label,
      cols: header.cols.map((col) => ({ key: fresh(), label: col.label })),
    })),
  ];
}

/** How many lines hold a quantity under `key` (a header counts its columns): the countdown's count. */
export function cellsUnder(
  headers: MatrixHeader[],
  key: string,
  lines: Array<MatrixCells | null | undefined>,
): number {
  const header = headers.find((row) => row.key === key);
  const keys = header ? (header.cols.length ? header.cols.map((col) => col.key) : [header.key]) : [key];
  return lines.filter((cells) => anyCell(cells, keys)).length;
}

/**
 * One line's cells and quantity after a column change, by the backend's rules (R12): the first
 * column ever added takes the line's quantity, removing the last puts the sum back, and anything
 * else drops cells under keys that are no longer leaves and re-sums. Used on lines staged in an
 * edit session, which the server's own move-in never sees.
 */
export function reshapeCells(
  before: MatrixHeader[] | null | undefined,
  after: MatrixHeader[] | null | undefined,
  cells: MatrixCells | null | undefined,
  quantity: string,
): { cells: MatrixCells | null; quantity: string } {
  const had = hasColumns(before);
  const has = hasColumns(after);
  if (!had && !has) return { cells: null, quantity };
  if (had && !has) return { cells: null, quantity: sumCells(cells, leafKeys(before)) };
  const keys = leafKeys(after);
  if (!had) {
    const qty = counted(quantity);
    const moved: MatrixCells = qty && compareMoney(qty, '0') === 1 ? { [keys[0]]: qty } : {};
    return { cells: moved, quantity: sumCells(moved) };
  }
  // A header that was its own quantity column (no columns) and now has some: its quantity moves
  // into its first column, unless that one already holds a value. The backend's `set_columns`
  // does exactly this; dropping it here made Save overwrite the server's move-in (B1).
  const source: MatrixCells = { ...(cells ?? {}) };
  const wasLeaf = new Set((before ?? []).filter((header) => header.cols.length === 0).map((header) => header.key));
  (after ?? []).forEach((header) => {
    if (!wasLeaf.has(header.key) || header.cols.length === 0) return;
    const moved = source[header.key];
    delete source[header.key];
    const first = header.cols[0].key;
    if (moved !== undefined && !(first in source)) source[first] = moved;
  });
  const kept: MatrixCells = {};
  keys.forEach((key) => {
    const value = counted(source[key]);
    if (value !== null && compareMoney(value, '0') !== 0) kept[key] = value;
  });
  return { cells: kept, quantity: sumCells(kept) };
}
