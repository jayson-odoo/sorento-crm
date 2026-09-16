/**
 * The Schedule matrix's own build step: rows x date buckets, out of the cells
 * `useOrderInquiryMatrix` already fetched (S3, PLAN-scm-oi-worklist-excel-parity.md).
 *
 * S3 moved the grouping server-side - `GET /order-inquiries/matrix` runs the GROUP BY
 * over the same filtered set the list reads, so there is no more row cap and no more
 * client-side grouping to keep in step with the server's own idea of a row. What is left
 * here is purely presentational: the distinct row/bucket headers the table needs, and
 * the date label a bucket's ISO `period` reads at the chosen granularity - the one thing
 * the server contract does not carry, because "3 Nov 2026" vs "Nov 2026" is a reading of
 * the SAME date, not a second fact about it.
 */
import { format, parseISO } from 'date-fns';
import type {
  OrderInquiryMatrixBucket,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryMatrixRow,
} from '../types/orderInquiry.types';

/** How a bucket's ISO start date reads at each granularity. */
function bucketLabelFor(period: string, granularity: OrderInquiryMatrixGranularity): string {
  const date = parseISO(period);
  if (granularity === 'day' || granularity === 'week') return format(date, 'd MMM yyyy');
  if (granularity === 'month') return format(date, 'MMM yyyy');
  return format(date, 'yyyy');
}

export interface OrderInquiryMatrix {
  rows: OrderInquiryMatrixRow[];
  buckets: OrderInquiryMatrixBucket[];
  cells: OrderInquiryMatrixCell[];
}

/**
 * The table's own row/bucket headers, read off the server's cells - never a second
 * fetch and never a second idea of what a row or a bucket is.
 */
export function buildOrderInquiryMatrix(
  cells: OrderInquiryMatrixCell[],
  granularity: OrderInquiryMatrixGranularity,
): OrderInquiryMatrix {
  const rowMap = new Map<string, OrderInquiryMatrixRow>();
  const bucketMap = new Map<string, OrderInquiryMatrixBucket>();

  for (const cell of cells) {
    if (!rowMap.has(cell.axis_key)) {
      rowMap.set(cell.axis_key, { key: cell.axis_key, label: cell.axis_label });
    }
    if (!bucketMap.has(cell.period)) {
      bucketMap.set(cell.period, {
        key: cell.period,
        label: bucketLabelFor(cell.period, granularity),
        start: cell.period,
      });
    }
  }

  return {
    rows: [...rowMap.values()].sort((a, b) => a.label.localeCompare(b.label)),
    buckets: [...bucketMap.values()].sort((a, b) => a.start.localeCompare(b.start)),
    cells,
  };
}
