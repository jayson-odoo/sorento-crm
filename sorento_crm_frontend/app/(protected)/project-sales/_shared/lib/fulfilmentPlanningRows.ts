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
import type { FulfilmentPlanningRow, PlanRow } from '../types/fulfilmentPlanning.types';
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

/**
 * Where the row's identity column links to: the sales order it names.
 *
 * The captain asked to reach the sales order from a row ("on click i should be able to view
 * the SO"). The row itself keeps its existing meaning - it opens the plan - and the identity
 * column becomes the link, which is what every other listing here does (the SCM sales-order
 * list and the purchase-order list both make the document number the way in).
 *
 * The CORE sales order wins when a row can reach both: it is the document the number on screen
 * belongs to, and an adopted planning record is a mirror of it rather than a second subject.
 * A row with neither answers null and renders as plain text - a dead link that looks like a way
 * in and answers with a 404 is worse than no link at all.
 */
export function planningRowSalesOrderHref(row: FulfilmentPlanningRow): string | null {
  if (row.sales_order_id) return `/scm/sales-orders/${row.sales_order_id}`;
  // The project route needs both halves; an adopted record has no project registration, so it
  // is simply not reachable that way (and it has a core order anyway).
  if (row.project_id && row.id) return `/project-sales/${row.project_id}/sales-orders/${row.id}`;
  return null;
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

/**
 * Where a Plans page row's identity column links to: the sales order it decided (D1).
 *
 * The PROJECT SO sheet wins when the decision's order has one - that page is the composition
 * itself and the one Amend lives on, which is what a row on this page is FOR. The plain SCM
 * document is the fallback, for the decisions this page also lists that belong to an order
 * nobody has registered to a project. A row with neither renders plain text rather than a link
 * that 404s.
 *
 * Deliberately the opposite priority from `planningRowSalesOrderHref`: that helper serves the
 * worklist, where the identity column's whole job is "open the underlying document" and the
 * core order is the more useful destination for a not-yet-planned row. Here the row already
 * IS a decision, so the sheet that shows its composition and its Amend is the more useful one.
 */
export function planRowHref(row: PlanRow): string | null {
  if (row.project_id && row.project_sales_order_id) {
    return `/project-sales/${row.project_id}/sales-orders/${row.project_sales_order_id}`;
  }
  if (row.sales_order_id) return `/scm/sales-orders/${row.sales_order_id}`;
  return null;
}
