'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { VERB_PALETTE_KEY } from '../../_shared/components/OrderInquiryVerbPill';
import { SupplyBar } from '../../_shared/components/SupplyBar';
import {
  KIND_COLOURS,
  KIND_LABELS,
  fullyLinked,
  kindText,
  segmentsOfRows,
} from '../../_shared/lib/orderInquiryKinds';
import { dominantVerbOf } from '../../_shared/lib/orderInquiryMatrix';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import type {
  OrderInquiryMatrixBucket,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixRow,
} from '../../_shared/types/orderInquiry.types';

const ROW_COL = 'w-[220px] min-w-[220px] max-w-[220px]';
/** A floor, not a fixed width - same reasoning as the fulfilment planning board's own
 * `DATE_COL`: `table-layout` is never `table-fixed`, so a narrow selection fills the
 * bordered container and a wide one overflows into the container's own horizontal scroll. */
const BUCKET_COL = 'min-w-[130px]';
const Z_PINNED = 'z-(--z-sticky-content)';
const Z_CORNER = 'z-(--z-sticky-content-corner)';

/**
 * Purchasing's own 2D schedule: by product, sales order, customer or agent down the side,
 * by day, week, month or year across the top - what the captain asked for in place of the
 * day-grid calendar this replaces ("vertically I can see by product, by sales order, by
 * customer, by agent, then horizontally is the dates").
 *
 * Modelled on `FulfilmentBoardMatrix` (sticky first column, sticky header row, `w-full`
 * with the row column fixed-width and the bucket columns carrying only a `min-w` floor),
 * for the same reasons documented there: the whole table scrolls inside this container
 * rather than the page, and the columns ARE data - there is one per bucket somebody
 * actually owes, never a full calendar grid.
 *
 * A BLANK CELL IS NOT A ZERO. It means no row in this selection lands on that row and
 * bucket, so it renders blank and stays blank.
 */
export function OrderInquiryScheduleMatrix({
  buckets,
  rows,
  rowHeader,
  cells,
  onOpenCell,
}: {
  buckets: OrderInquiryMatrixBucket[];
  rows: OrderInquiryMatrixRow[];
  rowHeader: string;
  cells: OrderInquiryMatrixCell[];
  onOpenCell: (cell: OrderInquiryMatrixCell) => void;
}) {
  const byKey = React.useMemo(() => {
    const map = new Map<string, OrderInquiryMatrixCell>();
    for (const cell of cells) map.set(`${cell.row_key}|${cell.bucket_key}`, cell);
    return map;
  }, [cells]);

  return (
    <div
      data-testid="order-inquiry-schedule-matrix"
      className="relative max-h-[70vh] w-full overflow-auto overscroll-x-contain rounded-lg border border-border"
    >
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th
              scope="col"
              className={cn(
                ROW_COL,
                Z_CORNER,
                'sticky left-0 top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
              )}
            >
              {rowHeader}
            </th>
            {buckets.map((bucket) => (
              <th
                key={bucket.key}
                scope="col"
                data-bucket={bucket.key}
                className={cn(
                  BUCKET_COL,
                  Z_PINNED,
                  'sticky top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
                )}
              >
                <span className="block truncate" title={bucket.label}>
                  {bucket.label}
                </span>
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th
                scope="row"
                className={cn(
                  ROW_COL,
                  Z_PINNED,
                  'sticky left-0 border-b border-e border-border bg-background px-2 py-1.5 text-start font-medium',
                )}
              >
                <span className="block truncate" title={row.description || row.label}>
                  {row.label}
                </span>
              </th>

              {buckets.map((bucket) => {
                const cell = byKey.get(`${row.key}|${bucket.key}`);
                return (
                  <td
                    key={bucket.key}
                    data-cell={`${row.key}|${bucket.key}`}
                    className="border-b border-e border-border p-0 align-top"
                  >
                    {cell ? <MatrixCellButton cell={cell} onOpen={() => onOpenCell(cell)} /> : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A cheap dot, coloured by whichever verb most of the cell's rows carry. */
const VERB_DOT_CLASS: Record<string, string> = {
  pending: 'bg-amber-500',
  processed_by_cs: 'bg-emerald-500',
  submitted: 'bg-sky-500',
  rejected: 'bg-red-500',
};

function MatrixCellButton({
  cell,
  onOpen,
}: {
  cell: OrderInquiryMatrixCell;
  onOpen: () => void;
}) {
  const rowCount = cell.rows.length;
  const dominantVerb = dominantVerbOf(cell.rows);
  const paletteKey = dominantVerb ? (VERB_PALETTE_KEY[dominantVerb] ?? 'draft') : 'draft';
  // What this cell's quantity still needs, the way the board reads a cell (AC-I12): a
  // segment per kind under the figure, and the same words beside it. Solid when every
  // row is wholly on a document, faded while any of it is still only an instruction.
  const segments = segmentsOfRows(cell.rows);
  const supply = kindText(segments);
  // The figure is what is STILL OWED here (`buildOrderInquiryMatrix` leaves a cancelled
  // row out of it), so it and the words under it always add up. The row count is the
  // whole cell all the same, cancelled rows included: it says what a click opens.
  const label = `${formatInquiryQty(cell.qty)} owed, ${rowCount} row${
    rowCount === 1 ? '' : 's'
  }${supply ? `, ${supply}` : ''}`;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      className="flex w-full items-start gap-1.5 px-2 py-1.5 text-start hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <span
        aria-hidden
        className={cn('mt-1 size-1.5 shrink-0 rounded-full', VERB_DOT_CLASS[paletteKey] ?? 'bg-muted-foreground')}
      />
      <span className="flex min-w-0 grow flex-col gap-0.5">
        <span className="font-medium tabular-nums">{formatInquiryQty(cell.qty)}</span>
        <SupplyBar
          segments={segments}
          decided={fullyLinked(cell.rows)}
          labels={KIND_LABELS}
          colours={KIND_COLOURS}
        />
        {/* The row count moves into the title beside the words: a cell is 130px wide and
            what to DO with the quantity is worth more of it than how many rows it is. */}
        <span className="truncate text-[11px] text-muted-foreground" title={label}>
          {supply || `${rowCount} row${rowCount === 1 ? '' : 's'}`}
        </span>
      </span>
    </button>
  );
}
