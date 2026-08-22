/**
 * The Stage 1 schedule matrix's own build step (PLAN-scm-loading-plan-demand-first.md, 6b.2):
 * the SAME `lines` the build already returned (`include_lines=true`), regrouped client-side -
 * mirrors `orderInquiryMatrix.ts`'s own reasoning: a different GROUPING of rows already on
 * hand, never a second fetch, so the matrix and its drill can never disagree about which lines
 * are in a cell.
 *
 * Two differences from the order-inquiry matrix this is modelled on: the axis is Product | SO
 * (not customer/agent - there is no agent on a container request line), and the "No date"
 * column sorts FIRST rather than last (captain's instruction for this screen specifically).
 */
import { format, parseISO, startOfMonth, startOfWeek } from 'date-fns';
import type { ContainerRequestSoLine } from '../../services/fulfilmentService';

export type ContainerRequestMatrixAxis = 'product' | 'order';
export type ContainerRequestMatrixGranularity = 'day' | 'week' | 'month';

const NO_DATE_KEY = 'no_date';

export interface ContainerRequestMatrixBucket {
  key: string;
  kind: 'dated' | 'no_date';
  label: string;
  /** ISO date of the bucket's start, dated buckets only - the ordering key. */
  start?: string | null;
}

/** One row, whichever axis produced it. `key` is never rendered; `label` is. */
export interface ContainerRequestMatrixRow {
  key: string;
  label: string;
  description?: string | null;
}

/** One cell: this row, by this bucket, across every line that lands there. */
export interface ContainerRequestMatrixCell {
  row_key: string;
  bucket_key: string;
  qty: number;
  lines: ContainerRequestSoLine[];
}

export interface ContainerRequestMatrix {
  rows: ContainerRequestMatrixRow[];
  buckets: ContainerRequestMatrixBucket[];
  cells: ContainerRequestMatrixCell[];
}

function bucketFor(
  line: ContainerRequestSoLine,
  granularity: ContainerRequestMatrixGranularity,
): ContainerRequestMatrixBucket {
  if (!line.required_date) {
    return { key: NO_DATE_KEY, kind: 'no_date', label: 'No date' };
  }
  const date = parseISO(line.required_date);
  if (granularity === 'day') {
    return {
      key: line.required_date,
      kind: 'dated',
      label: format(date, 'd MMM yyyy'),
      start: line.required_date,
    };
  }
  if (granularity === 'week') {
    const start = startOfWeek(date, { weekStartsOn: 1 });
    const key = format(start, 'yyyy-MM-dd');
    return { key, kind: 'dated', label: format(start, 'd MMM yyyy'), start: key };
  }
  const start = startOfMonth(date);
  const key = format(start, 'yyyy-MM');
  return { key, kind: 'dated', label: format(start, 'MMM yyyy'), start: format(start, 'yyyy-MM-dd') };
}

function axisKeyOf(
  line: ContainerRequestSoLine,
  axis: ContainerRequestMatrixAxis,
): { key: string; label: string; description?: string | null } {
  if (axis === 'order') {
    const label = line.so_number || 'Not numbered';
    return { key: line.so_number ? `so:${line.so_number}` : `unnumbered:${label}`, label, description: line.customer_label };
  }
  const label = line.item_code || 'Unresolved';
  return { key: line.item_code ? `item:${line.item_code}` : 'unresolved', label };
}

/** The whole matrix, built off the SO lines the build already returned. Columns are only the
 *  buckets somebody actually owes - never a full calendar grid.
 *
 *  `rankByProductId` (optional) mirrors the ranked demand table's own row order onto the
 *  product axis, so the schedule view and the table never disagree about which product comes
 *  first - a ranked product sorts by its rank, ascending; a product absent from the ranking
 *  (should not happen, but a stock-list product can outrun the ranking build) sorts after every
 *  ranked row, alphabetically among itself. The order axis (rows = SO numbers) has no rank to
 *  borrow and keeps its existing alphabetical sort regardless of this argument. */
export function buildContainerRequestMatrix(
  lines: ContainerRequestSoLine[],
  axis: ContainerRequestMatrixAxis,
  granularity: ContainerRequestMatrixGranularity,
  rankByProductId?: Map<string, number>,
): ContainerRequestMatrix {
  const rowMap = new Map<string, ContainerRequestMatrixRow>();
  const rowRank = new Map<string, number>();
  const bucketMap = new Map<string, ContainerRequestMatrixBucket>();
  const cellMap = new Map<
    string,
    { row_key: string; bucket_key: string; qty: number; lines: ContainerRequestSoLine[] }
  >();

  for (const line of lines) {
    const { key: rowKey, label: rowLabel, description } = axisKeyOf(line, axis);
    if (!rowMap.has(rowKey)) rowMap.set(rowKey, { key: rowKey, label: rowLabel, description });
    if (axis === 'product' && rankByProductId && !rowRank.has(rowKey)) {
      const rank = rankByProductId.get(line.product_id);
      if (rank !== undefined) rowRank.set(rowKey, rank);
    }

    const bucket = bucketFor(line, granularity);
    if (!bucketMap.has(bucket.key)) bucketMap.set(bucket.key, bucket);

    const cellKey = `${rowKey}|${bucket.key}`;
    const existing = cellMap.get(cellKey);
    if (existing) {
      existing.qty += line.qty;
      existing.lines.push(line);
    } else {
      cellMap.set(cellKey, { row_key: rowKey, bucket_key: bucket.key, qty: line.qty, lines: [line] });
    }
  }

  const buckets = [...bucketMap.values()].sort((a, b) => {
    // "No date" leads here (this screen's own rule) rather than trailing, so a line with no
    // required date is the first thing Ms Tee sees, not the last.
    if (a.kind === 'no_date') return b.kind === 'no_date' ? 0 : -1;
    if (b.kind === 'no_date') return 1;
    return (a.start ?? '').localeCompare(b.start ?? '');
  });

  const cells: ContainerRequestMatrixCell[] = [...cellMap.values()];

  const rows = [...rowMap.values()].sort((a, b) => {
    // Ranked rows lead, in rank order; a row with no rank on file sorts after every ranked
    // one and falls back to alphabetical among the other unranked rows.
    const rankA = rowRank.get(a.key);
    const rankB = rowRank.get(b.key);
    if (rankA !== undefined && rankB !== undefined) return rankA - rankB;
    if (rankA !== undefined) return -1;
    if (rankB !== undefined) return 1;
    return a.label.localeCompare(b.label);
  });

  return {
    rows,
    buckets,
    cells,
  };
}
