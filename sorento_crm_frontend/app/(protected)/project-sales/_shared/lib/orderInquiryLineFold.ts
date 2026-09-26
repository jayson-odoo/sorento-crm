import { ackStateOf } from './orderInquiryAck';
import { isInquiryBuyRow } from './orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';

/**
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248): the OI detail Lines tab reads like
 * the sales order's own Lines grid - ONE row per sales order line, whatever the split
 * (owner ruling 26 Sep 2026, G5). Pure and client-side over the rows the tab already
 * loads; no row is written or dropped, only grouped.
 *
 * A row is LIVE while `state != 'cancelled'` and it is not `redirected_to_pool`; every
 * other row of the line is history, read behind the line's one History icon (G1, G6).
 */

/** The four quantity columns (G4) plus how the line reads. */
export interface OrderInquiryLine {
  /** Stable grid row id: `line:<core_line_id>`, `so:<so_number>:<line_no>` or `row:<id>`. */
  key: string;
  lineNo: number | null;
  /** Every row of the line the Lines fetch returned (live and used; cancelled rows are
   * not in that fetch, the History dialog reads them separately). */
  rows: OrderInquiryWorklistRow[];
  liveRows: OrderInquiryWorklistRow[];
  historyRows: OrderInquiryWorklistRow[];
  /** Addresses the line's reserve actions, Raised via, Delivery date, Supplier, Location
   * and product: the reserve-bearing live buy row, else the most urgent live buy row,
   * else the first live row, else the first row. */
  primary: OrderInquiryWorklistRow;
  /** The row whose verb is the line's Instruction (CANCEL_BALANCE > CHANGE_SO > DELAY >
   * ADVANCE > the primary row's own verb). */
  instructionRow: OrderInquiryWorklistRow;
  /** Most urgent live state, or `line_cancelled` / `nothing_to_buy`. */
  state: string;
  lineCancelled: boolean;
  /** Greyed on the grid: a cancelled line (G7) or one with nothing left to buy (O2). */
  muted: boolean;
  soQty: number;
  /** MOCK(S1): true while the payload carries no `so_line_qty`. */
  soQtyMocked: boolean;
  requested: number;
  taken: number;
  remaining: number;
  bundled: number;
}

/** What the grid itself renders: the primary row's fields plus its line. A plain row
 * (no `line`) is read as a line of one, see `lineOf`. */
export type OrderInquiryLineRow = OrderInquiryWorklistRow & { line?: OrderInquiryLine };

const STATE_URGENCY = ['raised', 'partly_linked', 'placed', 'actioned'];
const RESERVE_URGENCY = ['requested', 'reserved', 'declined'];
const INSTRUCTION_URGENCY = ['CANCEL_BALANCE', 'CHANGE_SO', 'DELAY', 'ADVANCE'];

function rank(list: string[], value: string | null | undefined): number {
  const index = value ? list.indexOf(value) : -1;
  return index === -1 ? list.length : index;
}

function num(value: string | null | undefined): number {
  return Number(value ?? '0') || 0;
}

export function isLiveInquiryRow(row: OrderInquiryWorklistRow): boolean {
  return row.state !== 'cancelled' && !row.redirected_to_pool;
}

/**
 * Which sales order line a row belongs to. The worklist row carries no `so_line_id`; it
 * carries `core_line_id`, the core line the server resolved off the row's mirror
 * `so_line_id` (one-to-one), and `line_no`. A row that names neither is a line of its own.
 */
export function foldKeyOf(row: OrderInquiryWorklistRow): string {
  if (row.core_line_id) return `line:${row.core_line_id}`;
  if (row.line_no != null) return `so:${row.so_number ?? ''}:${row.line_no}`;
  return `row:${row.id}`;
}

function pickPrimary(live: OrderInquiryWorklistRow[], all: OrderInquiryWorklistRow[]) {
  const buy = live.filter((row) => isInquiryBuyRow(row.verb));
  const byReserve = [...buy].sort(
    (a, b) => rank(RESERVE_URGENCY, a.reserve_state) - rank(RESERVE_URGENCY, b.reserve_state),
  );
  if (byReserve[0]?.reserve_state && RESERVE_URGENCY.includes(byReserve[0].reserve_state)) {
    return byReserve[0];
  }
  const byState = [...buy].sort(
    (a, b) => rank(STATE_URGENCY, a.state) - rank(STATE_URGENCY, b.state),
  );
  return byState[0] ?? live[0] ?? all[0];
}

function buildLine(key: string, rows: OrderInquiryWorklistRow[]): OrderInquiryLine {
  const liveRows = rows.filter(isLiveInquiryRow);
  const historyRows = rows.filter((row) => !isLiveInquiryRow(row));
  const liveBuy = liveRows.filter((row) => isInquiryBuyRow(row.verb));
  const primary = pickPrimary(liveRows, rows);
  const lineCancelled = rows.some((row) => row.line_cancelled);

  const asked = liveBuy.reduce((total, row) => total + num(row.qty), 0);
  const taken = liveBuy.reduce(
    (total, row) => total + num(row.linked_qty) + num(row.reserved_qty),
    0,
  );
  const bundled = liveBuy.reduce((total, row) => total + num(row.bundled_qty), 0);
  // G7: a cancelled line's quantity is called off, not owed.
  const requested = lineCancelled ? 0 : asked;
  const remaining = lineCancelled ? 0 : Math.max(requested - taken - bundled, 0);

  const instructionRow =
    [...liveRows]
      .filter((row) => INSTRUCTION_URGENCY.includes(row.verb))
      .sort((a, b) => rank(INSTRUCTION_URGENCY, a.verb) - rank(INSTRUCTION_URGENCY, b.verb))[0] ??
    primary;

  let state: string;
  if (lineCancelled) state = 'line_cancelled';
  else if (liveRows.length === 0) state = 'nothing_to_buy';
  else state = pickPrimary(
    // The most urgent STATE, whatever row the reserve pill reads.
    liveBuy.map((row) => ({ ...row, reserve_state: null })),
    liveRows,
  ).state;

  // MOCK(S1): the worklist row carries no sales order line quantity yet
  // (`PLAN-oi-no-double-count-25sep.md` S1 adds `so_line_qty`). Until it does, SO Qty
  // reads what the line asked for - its live buy rows, else what its used rows held.
  const soLineQty = rows.find((row) => row.so_line_qty != null)?.so_line_qty;
  const usedAsked = historyRows
    .filter((row) => isInquiryBuyRow(row.verb) && row.state !== 'cancelled')
    .reduce((total, row) => total + num(row.qty), 0);
  const soQtyMocked = soLineQty == null;
  const soQty = soQtyMocked ? asked || usedAsked : num(soLineQty);

  return {
    key,
    lineNo: primary.line_no ?? null,
    rows,
    liveRows,
    historyRows,
    primary,
    instructionRow,
    state,
    lineCancelled,
    muted: lineCancelled || liveRows.length === 0,
    soQty,
    soQtyMocked,
    requested,
    taken,
    remaining,
    bundled: lineCancelled ? 0 : bundled,
  };
}

/** Groups rows into lines, sorted by sales order line No.; lines with no No. sort last, in
 * the order their rows arrived. */
export function foldInquiryLines(rows: OrderInquiryWorklistRow[]): OrderInquiryLine[] {
  const groups = new Map<string, OrderInquiryWorklistRow[]>();
  for (const row of rows) {
    const key = foldKeyOf(row);
    const group = groups.get(key);
    if (group) group.push(row);
    else groups.set(key, [row]);
  }
  const lines = [...groups.entries()].map(([key, group]) => buildLine(key, group));
  return lines
    .map((line, index) => ({ line, index }))
    .sort((a, b) => {
      const an = a.line.lineNo ?? Number.POSITIVE_INFINITY;
      const bn = b.line.lineNo ?? Number.POSITIVE_INFINITY;
      return an === bn ? a.index - b.index : an - bn;
    })
    .map(({ line }) => line);
}

/** The grid's data: the primary row's own fields, so every shared cell renderer reads it
 * unchanged, plus the line. */
export function toLineRows(lines: OrderInquiryLine[]): OrderInquiryLineRow[] {
  return lines.map((line) => ({ ...line.primary, line }));
}

export function lineOf(row: OrderInquiryLineRow): OrderInquiryLine {
  return row.line ?? buildLine(foldKeyOf(row), [row]);
}

/** Footer totals (AC-ND-17): cancelled lines excluded; Remaining is the footer's own
 * subtraction, the same rule `inquiryFooterTotals` states for rows. */
export function lineFooterTotals(lines: OrderInquiryLine[]) {
  const counted = lines.filter((line) => !line.lineCancelled);
  const soQty = counted.reduce((total, line) => total + line.soQty, 0);
  const requested = counted.reduce((total, line) => total + line.requested, 0);
  const taken = counted.reduce((total, line) => total + line.taken, 0);
  const bundled = counted.reduce((total, line) => total + line.bundled, 0);
  return { soQty, requested, taken, remaining: Math.max(requested - taken - bundled, 0) };
}

/**
 * G6 (owner ruling 26 Sep): confirming a line also confirms its used rows still in
 * `changed`, so the header never waits on a row nobody can see on the main grid.
 */
export function usedRowIdsToConfirm(
  rows: OrderInquiryWorklistRow[],
  selectedRowIds: string[],
): string[] {
  if (selectedRowIds.length === 0) return [];
  const selected = new Set(selectedRowIds);
  const keys = new Set(rows.filter((row) => selected.has(row.id)).map(foldKeyOf));
  return rows
    .filter(
      (row) =>
        row.redirected_to_pool &&
        row.state !== 'cancelled' &&
        !selected.has(row.id) &&
        ackStateOf(row) === 'changed' &&
        keys.has(foldKeyOf(row)),
    )
    .map((row) => row.id);
}

export type LineHistoryWhat =
  | 'Now'
  | 'Used'
  | 'Superseded'
  | 'Re-raised'
  | 'Cancelled'
  | 'Cancel balance'
  | 'Line cancelled';

export interface LineHistoryEntry {
  row: OrderInquiryWorklistRow;
  what: LineHistoryWhat;
  why: string;
}

function whatOf(row: OrderInquiryWorklistRow): LineHistoryWhat {
  if (row.line_cancelled) return 'Line cancelled';
  if (row.redirected_to_pool) return 'Used';
  if (row.state === 'cancelled') {
    if (row.verb === 'CANCEL_BALANCE') return 'Cancel balance';
    const note = row.note ?? '';
    if (/re-?raised/i.test(note)) return 'Re-raised';
    if (/superseded/i.test(note)) return 'Superseded';
    return 'Cancelled';
  }
  return 'Now';
}

function newestFirst(a: OrderInquiryWorklistRow, b: OrderInquiryWorklistRow) {
  return (b.raised_at ?? '').localeCompare(a.raised_at ?? '');
}

/**
 * The History dialog's Rows tab (AC-ND-15): the line's live rows first as Now, then every
 * retired row, newest first. `cancelledRows` is the inquiry's cancelled set (the Lines
 * fetch does not carry it); only this line's rows are kept. A Now row with a
 * `previous_qty` reads "Was <n>." before its note - the only place the Was / now story
 * shows (G1).
 */
export function lineHistoryEntries(
  line: OrderInquiryLine,
  cancelledRows: OrderInquiryWorklistRow[],
): LineHistoryEntry[] {
  const own = cancelledRows.filter(
    (row) => foldKeyOf(row) === line.key && !line.rows.some((r) => r.id === row.id),
  );
  const toEntry = (row: OrderInquiryWorklistRow): LineHistoryEntry => {
    const what = whatOf(row);
    const note = row.note ?? '';
    const was = what === 'Now' && row.previous_qty != null ? `Was ${num(row.previous_qty)}.` : '';
    return { row, what, why: [was, note].filter(Boolean).join(' ') };
  };
  const now = line.liveRows.filter((row) => !row.line_cancelled);
  const retired = [...line.rows.filter((row) => !now.includes(row)), ...own].sort(newestFirst);
  return [...now.map(toEntry), ...retired.map(toEntry)];
}
