/**
 * Reading a row on purchasing's cross-project order inquiry.
 *
 * Pure, and deliberately outside the grid: where a row LINKS is the thing that decides
 * whether the screen is usable at all (an adopted order has no project, so the project
 * route cannot reach it), and the month vocabulary has to match the tab names on the
 * spreadsheet purchasing already works from. Both are worth asserting without mounting a
 * table.
 */
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';

/**
 * The sheet's own spelling of a month, not the browser's: their tabs read `JAN 26`,
 * `JUNE 26`, `JULY 26`, `SEPT 26`. The backend labels every month it returns, so this is
 * only the fallback for a month the summary did not name.
 */
const MONTH_WORD = [
  'JAN',
  'FEB',
  'MAR',
  'APR',
  'MAY',
  'JUNE',
  'JULY',
  'AUG',
  'SEPT',
  'OCT',
  'NOV',
  'DEC',
];

/** `2026-01` to `JAN 26`. Anything that is not a month answers null rather than guessing. */
export function deliveryMonthLabel(month?: string | null): string | null {
  if (!month) return null;
  const match = /^(\d{4})-(\d{2})$/.exec(month.trim());
  if (!match) return null;
  const index = Number(match[2]) - 1;
  if (index < 0 || index > 11) return null;
  return `${MONTH_WORD[index]} ${match[1].slice(2)}`;
}

/**
 * Where the row's sales-order column links to.
 *
 * The CORE sales order wins whenever the row can reach both, for the same reason it does
 * on the planning worklist: it is the document the number on screen belongs to, and the
 * project mirror is a mirror of it rather than a second subject. An adopted row has no
 * project at all, so the project route could never reach it. A row with neither renders
 * as plain text - a link that answers 404 is worse than no link.
 */
export function orderInquiryRowHref(row: OrderInquiryWorklistRow): string | null {
  if (row.core_sales_order_id) return `/scm/sales-orders/${row.core_sales_order_id}`;
  if (row.project_id && row.project_sales_order_id) {
    return `/project-sales/${row.project_id}/sales-orders/${row.project_sales_order_id}`;
  }
  return null;
}

/** A quantity as a person reads it: `600`, never `600.0000`. */
export function formatInquiryQty(qty?: string | null): string {
  if (qty === null || qty === undefined) return '';
  const text = String(qty).trim();
  if (text === '') return '';
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  return text.includes('.') ? text.replace(/\.?0+$/, '') : text;
}

/**
 * Why "Taken from PO" / "Remaining" should NOT print a figure for this row's own verb
 * (the captain, 21 Aug: an ADVANCE row read "Taken from PO 432 / Remaining 0" - both real
 * `ORDER`-sibling totals on the same SO line, correctly summed, but sitting beside an
 * unactioned date change they read as "fully handled"). Both aggregates are scoped to
 * `verb = 'ORDER'` siblings only
 * (`OrderInquiryWorklistService._quantity_flow_by_so_line`), so any other verb's row is
 * shown what that scoping actually means for it, rather than a number that looks like an
 * answer about ITSELF. `null` for an `ORDER` row - it IS what the aggregate is about, so
 * the figure stands.
 */
const NON_ORDER_FLOW_LABEL: Record<string, string> = {
  ADVANCE: 'Date change',
  DELAY: 'Date change',
  CHANGE_SO: 'SO changed',
  CANCEL_BALANCE: 'Balance cancelled',
  PRE_ORDERED_DO_NOT_ORDER: 'Pre-ordered',
  ALREADY_INBOUND: 'Already inbound',
  RELEASE: 'Released',
};

export function flowExclusionLabel(verb: string): string | null {
  if (verb === 'ORDER') return null;
  return NON_ORDER_FLOW_LABEL[verb] ?? 'Not an ORDER row';
}
