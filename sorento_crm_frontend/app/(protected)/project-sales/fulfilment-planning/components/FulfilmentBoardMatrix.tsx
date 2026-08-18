'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { bucketLabelText } from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardDateBucket,
  BoardProductRow,
} from '../../_shared/types/fulfilmentPlanning.types';

const PRODUCT_COL = 'w-[190px] min-w-[190px] max-w-[190px]';
const DATE_COL = 'w-[150px] min-w-[150px] max-w-[150px]';

/**
 * Two paint layers, and every pinned cell names the one it is on. A cell pinned on BOTH axes
 * (the "Product" corner) has to beat a cell pinned on one, because with equal z-index the
 * winner is whichever the DOM happened to put last rather than whichever a reader expects.
 * Same rule, and the same reason, as the delivery-schedule matrix.
 */
const Z_PINNED = 'z-20';
const Z_CORNER = 'z-30';

/**
 * A pinned cell has to be OPAQUE. `bg-destructive/10` is ninety percent transparent, so a
 * quantity scrolling underneath a pinned header shows straight through it and reads as a
 * number appearing in the header. `color-mix` gives the same tint with actual paint on it, and
 * is also the only way to tint these tokens: Tailwind v4 resolves them to `oklch(...)`, so
 * `hsl(var(--destructive) / 0.1)` is dropped by the browser as invalid.
 */
const PAST_HEADER_BG = 'bg-[color-mix(in_oklab,var(--destructive)_12%,var(--muted))]';
const NO_DATE_BG = 'bg-[color-mix(in_oklab,var(--foreground)_6%,var(--muted))]';

/**
 * The body tint for a bucket that is already past. Lighter than the header, and still opaque:
 * a `/5` alpha over a scrolling body reads as a smudge rather than as a column.
 */
const PAST_CELL_BG = 'bg-[color-mix(in_oklab,var(--destructive)_6%,var(--background))]';

/**
 * The planning board: DATE BUCKETS across the top, PRODUCTS down the side, each cell the
 * quantity of that product owed by that date across every selected sales order (PLAN 13).
 *
 * The axis words are `dateBuckets` and `productRows` deliberately. The delivery-schedule
 * matrix calls a PRODUCT a `column` - its API's word, kept on purpose even after that grid was
 * transposed to this same orientation - so borrowing its vocabulary here would leave two grids
 * in the same module using one word for opposite things.
 *
 * NOT a DataGrid, and this is the same carve-out that file documents: here the COLUMNS ARE
 * DATA. There is one per date bucket, there are as many as the selection needs, and no column
 * config, sort or resize applies to them. What DataGrid would otherwise give us is solved
 * explicitly, and those three obligations are the price of the carve-out:
 *
 *   - the whole table scrolls INSIDE this container, so the page body never scrolls sideways;
 *   - the product column is sticky and the header row is sticky, both opaque, so a reader
 *     eight buckets in still knows which product they are on;
 *   - fixed widths on a `w-max` table, never `table-fixed`, which overlaps its columns the
 *     moment content exceeds the declared width.
 *
 * A BLANK CELL IS NOT A ZERO. It means no selected order owes that product by that date, so it
 * renders blank and stays blank.
 *
 * THE PAST IS TINTED, NOT MERGED. Every dated bucket is a real date, however far back, and the
 * server's `is_past` is the only thing this grid colours on. The board used to carry one
 * aggregate Overdue column and it collapsed a whole selection into it - 160 of 160 lines, with
 * their dates gone. The cost of the change is columns, and the board pays it: it spans years,
 * so the horizontal scroll below is load-bearing rather than a nicety.
 */
export function FulfilmentBoardMatrix({
  dateBuckets,
  productRows,
  cells,
  decidedKeys,
  onOpenCell,
}: {
  dateBuckets: BoardDateBucket[];
  productRows: BoardProductRow[];
  cells: BoardCell[];
  /** Contribution keys that carry a verdict, so a fully-decided cell can say so. */
  decidedKeys: Set<string>;
  onOpenCell: (cell: BoardCell) => void;
}) {
  const byKey = React.useMemo(() => {
    const map = new Map<string, BoardCell>();
    for (const cell of cells) map.set(`${cell.item_code}|${cell.bucket_key}`, cell);
    return map;
  }, [cells]);

  return (
    <div
      data-testid="fulfilment-board-matrix"
      className="relative max-h-[70vh] w-full overflow-auto overscroll-x-contain rounded-lg border border-border"
    >
      <table className="w-max border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th
              scope="col"
              className={cn(
                PRODUCT_COL,
                Z_CORNER,
                'sticky left-0 top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
              )}
            >
              Product
            </th>
            {dateBuckets.map((bucket) => (
              <th
                key={bucket.key}
                scope="col"
                data-bucket={bucket.key}
                data-past={String(Boolean(bucket.is_past))}
                className={cn(
                  DATE_COL,
                  Z_PINNED,
                  'sticky top-0 border-b border-e border-border px-2 py-2 text-start align-bottom font-medium',
                  bucket.kind === 'no_date'
                    ? NO_DATE_BG
                    : bucket.is_past
                      ? PAST_HEADER_BG
                      : 'bg-muted',
                )}
              >
                <span className="block truncate" title={bucketLabelText(bucket.label)}>
                  {bucketLabelText(bucket.label)}
                </span>
                {(bucket.kind === 'no_date' || bucket.is_past) && (
                  <span className="block truncate text-[11px] font-normal text-muted-foreground">
                    {bucket.kind === 'no_date' ? 'Not stated' : 'Already past'}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {productRows.map((product) => (
            <tr key={product.item_code}>
              <th
                scope="row"
                className={cn(
                  PRODUCT_COL,
                  Z_PINNED,
                  'sticky left-0 border-b border-e border-border bg-background px-2 py-1.5 text-start font-medium',
                )}
              >
                <span className="block truncate" title={product.item_code}>
                  {product.item_code}
                </span>
              </th>

              {dateBuckets.map((bucket) => {
                const cell = byKey.get(`${product.item_code}|${bucket.key}`);
                return (
                  <td
                    key={bucket.key}
                    data-cell={`${product.item_code}|${bucket.key}`}
                    className={cn(
                      DATE_COL,
                      'border-b border-e border-border p-0 align-top',
                      bucket.is_past && PAST_CELL_BG,
                    )}
                  >
                    {cell ? (
                      <BoardCellButton
                        cell={cell}
                        decidedKeys={decidedKeys}
                        onOpen={() => onOpenCell(cell)}
                      />
                    ) : null}
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

/**
 * One cell: the quantity, then the source strip that answers "where will I need to source to
 * fulfil" without anybody having to click (journey step 3).
 *
 * A cell is a button because clicking it is the whole interaction, and a div with an onClick
 * is not reachable from a keyboard.
 */
function BoardCellButton({
  cell,
  decidedKeys,
  onOpen,
}: {
  cell: BoardCell;
  decidedKeys: Set<string>;
  onOpen: () => void;
}) {
  const decided = cell.contributions.filter((entry) => decidedKeys.has(entry.key)).length;
  const strip = cell.locations
    .map((entry) => `${entry.location ?? 'No location'} ${entry.qty}`)
    .join(' · ');
  const orders = new Set(cell.contributions.map((entry) => entry.so_number)).size;
  const label = `${cell.item_code}, ${cell.total_qty} across ${orders} sales order${
    orders === 1 ? '' : 's'
  }`;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      className="flex w-full flex-col gap-0.5 px-2 py-1.5 text-start hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <span className="flex items-baseline gap-1.5">
        <span className="font-medium tabular-nums">{cell.total_qty}</span>
        <span className="text-[11px] text-muted-foreground">
          {orders === 1 ? '1 order' : `${orders} orders`}
        </span>
      </span>

      {/* The source strip. One entry per distinct location, because one cell legitimately
          spans several: the location is the line's own, and lines from different orders do
          not have to agree about it (PLAN 13.7). */}
      <span className="block truncate text-[11px] text-muted-foreground" title={strip}>
        {strip}
      </span>

      <span className="flex flex-wrap gap-1">
        {cell.unplannable_count > 0 && (
          <span className="rounded bg-destructive/10 px-1 text-[10px] font-medium text-destructive">
            {`${cell.unplannable_count} need${cell.unplannable_count === 1 ? 's' : ''} a location`}
          </span>
        )}
        {cell.contested_count > 0 && (
          <span className="rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">
            {`${cell.contested_count} contested`}
          </span>
        )}
        {decided > 0 && (
          <span className="rounded bg-emerald-100 px-1 text-[10px] font-medium text-emerald-800">
            {`${decided}/${cell.contributions.length} decided`}
          </span>
        )}
      </span>
    </button>
  );
}
