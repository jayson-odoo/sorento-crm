/**
 * Reading a worklist row that came from either arm of the union.
 *
 * The worklist is one list of two kinds of subject (PLAN-fulfilment-planning-from-autocount-so
 * section 6): an outstanding CORE sales order, which may or may not have been planned yet, and a
 * planning record that has no core sales order at all. They share a row shape, and almost every
 * field a planning record carries is one a not-started core order genuinely does not have. These
 * helpers are the single place that decides what to read when.
 *
 * Pure, and deliberately separate from the grid: the ordering rule in particular is an acceptance
 * criterion (AC-FP04, total and stable) and is worth asserting without mounting a table.
 */
import type { FulfilmentPlanningRow } from '../types/fulfilmentPlanning.types';
import { fromMinor, toMinor } from './supplyComposition';

/**
 * The row's stable key for the grid.
 *
 * A not-started row has no planning record and therefore no `id`, so the core sales order is the
 * identity; once it is adopted the same subject gains an `id` and keeps its place. Falling back
 * through the human key last means a row can never collide with another or land on no key at all,
 * which is what puts a row on two pages or on neither.
 */
export function planningRowKey(row: FulfilmentPlanningRow): string {
  return (
    row.id || row.sales_order_id || row.so_number || row.provisional_ref || row.autocount_doc_no || ''
  );
}

/**
 * What the row is CALLED on screen: the AutoCount sales-order number when there is one, else the
 * document number, else our own provisional reference. Never an id.
 */
export function planningRowReference(row: FulfilmentPlanningRow): string | null {
  return row.so_number || row.autocount_doc_no || row.provisional_ref || null;
}

/** The project this order is for, by name when it is registered and by the sheet's string when not. */
export function planningRowProjectLabel(row: FulfilmentPlanningRow): string | null {
  return row.project_label || row.project_name || null;
}

/** Nobody has planned this order yet, so the row's one action is Start planning. */
export function isNotStarted(row: FulfilmentPlanningRow): boolean {
  return row.review_state === 'not_started';
}

/**
 * A quantity as a person reads it: "5488", not "5488.0000".
 *
 * Goes through the shared minor-unit helpers rather than a local regex so the worklist total and
 * the sheet's line quantities round the same way.
 */
export function formatOutstandingQty(qty?: string | null): string | null {
  if (qty === null || qty === undefined || String(qty).trim() === '') return null;
  return fromMinor(toMinor(qty));
}

/**
 * AC-FP04: earliest still-owed required date first, undated last, tie-broken on the sales-order
 * number so the order is TOTAL. An unstable order is what puts one row on two pages of a paged
 * list and another on none.
 *
 * The server orders the real list; this exists because the ordering is a promise the screen makes
 * and a promise is worth a test, and because the mock has to make the same one.
 */
export function sortByEarliestRequired(
  rows: FulfilmentPlanningRow[],
): FulfilmentPlanningRow[] {
  return [...rows].sort((left, right) => {
    const leftDate = left.earliest_required_date ?? null;
    const rightDate = right.earliest_required_date ?? null;
    if (leftDate !== rightDate) {
      if (leftDate === null) return 1;
      if (rightDate === null) return -1;
      return leftDate < rightDate ? -1 : 1;
    }
    return (planningRowReference(left) ?? '').localeCompare(planningRowReference(right) ?? '');
  });
}
