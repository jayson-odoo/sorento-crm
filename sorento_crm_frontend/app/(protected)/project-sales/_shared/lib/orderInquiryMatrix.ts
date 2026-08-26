/**
 * The Schedule matrix's own build step: rows x date buckets, out of the worklist rows
 * already on hand.
 *
 * Pure and client-side on purpose, mirroring `fulfilmentBoard.ts`'s `boardAxis` - this is
 * a different GROUPING of the same rows the list already fetched (unpaged, one request),
 * never a second fetch and never a second idea of what a row is. Because the grouping runs
 * here, a cell's own `rows` are exactly what a click drills down to: no server round trip,
 * and no risk of the matrix and the drilldown disagreeing about which rows are in a cell.
 */
import { format, parseISO, startOfMonth, startOfWeek, startOfYear } from 'date-fns';
import { CANCELLED_STATE } from './orderInquiryKinds';
import { fromMinor, toMinor } from './supplyComposition';
import type {
  OrderInquiryMatrixAxis,
  OrderInquiryMatrixBucket,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryMatrixRow,
  OrderInquiryWorklistRow,
} from '../types/orderInquiry.types';

const NO_DATE_KEY = 'no_date';

/** The column a row's delivery date lands in, at the chosen granularity. */
function bucketFor(
  row: OrderInquiryWorklistRow,
  granularity: OrderInquiryMatrixGranularity,
): OrderInquiryMatrixBucket {
  if (!row.delivery_date) {
    return { key: NO_DATE_KEY, kind: 'no_date', label: 'No date' };
  }
  const date = parseISO(row.delivery_date);
  if (granularity === 'day') {
    return { key: row.delivery_date, kind: 'dated', label: format(date, 'd MMM yyyy'), start: row.delivery_date };
  }
  if (granularity === 'week') {
    const start = startOfWeek(date, { weekStartsOn: 1 });
    const key = format(start, 'yyyy-MM-dd');
    return { key, kind: 'dated', label: format(start, 'd MMM yyyy'), start: key };
  }
  if (granularity === 'month') {
    const start = startOfMonth(date);
    const key = format(start, 'yyyy-MM');
    return { key, kind: 'dated', label: format(start, 'MMM yyyy'), start: format(start, 'yyyy-MM-dd') };
  }
  const start = startOfYear(date);
  const key = format(start, 'yyyy');
  return { key, kind: 'dated', label: key, start: format(start, 'yyyy-MM-dd') };
}

/**
 * How one row is keyed and labelled on each axis.
 *
 * `key` is never rendered (no UUIDs in the UI); `label` is what the reader sees. Where the
 * worklist row carries no id for the grouping (customer, which is printed as one combined
 * "project / customer" string rather than as a separate field), the label becomes the key -
 * the same stated compromise the planning board's own pivot takes for the same reason.
 */
function axisKeyOf(
  row: OrderInquiryWorklistRow,
  axis: OrderInquiryMatrixAxis,
): { key: string; label: string; description?: string | null } {
  if (axis === 'sales_order') {
    const label = row.so_number || 'Not numbered';
    const key = row.core_sales_order_id || row.project_sales_order_id || `so:${label}`;
    return { key, label };
  }
  if (axis === 'customer') {
    const label = row.project_customer || 'Not attributed';
    return { key: row.project_id ? `project:${row.project_id}` : `name:${label}`, label };
  }
  if (axis === 'agent') {
    const label = row.agent_code || 'No agent';
    return { key: row.agent_code || 'no_agent', label, description: row.agent_label };
  }
  const label = row.item_code || 'Unresolved';
  return { key: row.item_code || 'unresolved', label, description: row.product_name };
}

export interface OrderInquiryMatrix {
  rows: OrderInquiryMatrixRow[];
  buckets: OrderInquiryMatrixBucket[];
  cells: OrderInquiryMatrixCell[];
}

/**
 * The whole matrix, built off the filtered worklist rows already fetched.
 *
 * Columns are only the buckets somebody actually owes (the planning board's own rule):
 * never a full calendar grid, so a filtered set spanning three weeks shows three columns.
 */
export function buildOrderInquiryMatrix(
  rows: OrderInquiryWorklistRow[],
  axis: OrderInquiryMatrixAxis,
  granularity: OrderInquiryMatrixGranularity,
): OrderInquiryMatrix {
  const rowMap = new Map<string, OrderInquiryMatrixRow>();
  const bucketMap = new Map<string, OrderInquiryMatrixBucket>();
  const cellMap = new Map<string, { row_key: string; bucket_key: string; rows: OrderInquiryWorklistRow[] }>();

  for (const row of rows) {
    const { key: rowKey, label: rowLabel, description } = axisKeyOf(row, axis);
    if (!rowMap.has(rowKey)) rowMap.set(rowKey, { key: rowKey, label: rowLabel, description });

    const bucket = bucketFor(row, granularity);
    if (!bucketMap.has(bucket.key)) bucketMap.set(bucket.key, bucket);

    const cellKey = `${rowKey}|${bucket.key}`;
    const existing = cellMap.get(cellKey);
    if (existing) existing.rows.push(row);
    else cellMap.set(cellKey, { row_key: rowKey, bucket_key: bucket.key, rows: [row] });
  }

  const buckets = [...bucketMap.values()].sort((a, b) => {
    // `no_date` is the one bucket with no place on a timeline, pinned last (the planning
    // board's own rule for the same reason).
    if (a.kind === 'no_date') return b.kind === 'no_date' ? 0 : 1;
    if (b.kind === 'no_date') return -1;
    return (a.start ?? '').localeCompare(b.start ?? '');
  });

  // A CELL'S FIGURE IS WHAT IS STILL OWED IN IT, so a cancelled row adds nothing to it -
  // the same rule `kindTotals` reads, and the reason the two agree: a headline of 91 over
  // a bar that reads "Buy 85" is a cell nobody can act on, because the six that make up
  // the difference were called off. The cell keeps EVERY row in `rows` all the same: the
  // drilldown is where a person goes to see what happened to them.
  const cells: OrderInquiryMatrixCell[] = [...cellMap.values()].map((entry) => ({
    row_key: entry.row_key,
    bucket_key: entry.bucket_key,
    qty: fromMinor(
      entry.rows.reduce(
        (total, row) => (row.state === CANCELLED_STATE ? total : total + toMinor(row.qty)),
        0,
      ),
    ),
    rows: entry.rows,
  }));

  return {
    rows: [...rowMap.values()].sort((a, b) => a.label.localeCompare(b.label)),
    buckets,
    cells,
  };
}

/** The most common verb in a cell - what a cheap left-border colour reads off. */
export function dominantVerbOf(rows: OrderInquiryWorklistRow[]): string | undefined {
  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.verb, (counts.get(row.verb) ?? 0) + 1);
  let winner: string | undefined;
  let best = 0;
  for (const [verb, count] of counts) {
    if (count > best) {
      best = count;
      winner = verb;
    }
  }
  return winner;
}
