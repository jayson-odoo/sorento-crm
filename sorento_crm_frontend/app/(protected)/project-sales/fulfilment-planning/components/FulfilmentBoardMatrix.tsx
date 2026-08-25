'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { bucketLabelText } from '../../_shared/lib/fulfilmentBoard';
import { toMinor } from '../../_shared/lib/supplyComposition';
import { BoardDecidedMarker, decidedRevisions } from './BoardDecidedMarker';
import { SupplyBar } from './SupplyBar';
import { COLOURS, cellSupply, dominant, dominantText } from '../../_shared/lib/supplyVocabulary';
import type {
  BoardAxisRow,
  BoardCell,
  BoardDateBucket,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

const PRODUCT_COL = 'w-[190px] min-w-[190px] max-w-[190px]';
/**
 * A FLOOR, not a fixed width. With `table` at `w-full` and `table-layout` left at its browser
 * default (AUTO, never `table-fixed`), a date column below this width never happens - it can
 * only grow, splitting whatever space the product column did not take. Two selected weeks fill
 * the bordered container instead of sitting in a third of it with the rest blank; twenty weeks
 * push the table past the container's width and the container's own `overflow-auto` takes over,
 * exactly as it did before.
 */
const DATE_COL = 'min-w-[150px]';

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

/*
 * NO BODY TINT FOR A PAST BUCKET. The column header carries it and says "Already past", which
 * is where the fact belongs; on the cells it collided with the supply bar, where rose means Buy
 * and nothing else (PLAN section C, AC-C4). One rose on a cell, one meaning.
 */

/**
 * The planning board: DATE BUCKETS across the top, PRODUCTS down the side, each cell the
 * quantity of that product owed by that date across every selected sales order (PLAN 13).
 *
 * The axis words are `dateBuckets` and `rows` deliberately. The delivery-schedule matrix calls
 * a PRODUCT a `column` - its API's word, kept on purpose even after that grid was transposed to
 * this same orientation - so borrowing its vocabulary here would leave two grids in the same
 * module using one word for opposite things.
 *
 * The vertical axis is no longer always products: it pivots to sales order, customer or project
 * (the captain: "how about if we want vertical is sales order, is customer, is project"). Each
 * row carries a `key` that is an id and a `label` that is what the reader sees, so two customers
 * with one name are two rows and neither shows an id.
 *
 * NOT a DataGrid, and this is the same carve-out that file documents: here the COLUMNS ARE
 * DATA. There is one per date bucket, there are as many as the selection needs, and no column
 * config, sort or resize applies to them. What DataGrid would otherwise give us is solved
 * explicitly, and those three obligations are the price of the carve-out:
 *
 * - the whole table scrolls INSIDE this container, so the page body never scrolls sideways;
 * - the product column is sticky and the header row is sticky, both opaque, so a reader
 *     eight buckets in still knows which product they are on;
 * - the table is `w-full` so a selection of two weeks fills the bordered container rather
 *     than sitting in a third of it with the rest blank (measured live), the product column
 *     keeps a fixed width because it is not part of what should stretch, and the date columns
 *     carry only a `min-w` floor so they grow evenly into whatever is left. `table-layout` is
 *     never `table-fixed`, which overlaps its columns the moment content exceeds the declared
 *     width - a wide selection still overflows past the floor and the container's own
 *     `overflow-auto` takes it from there, unchanged from before.
 *
 * A BLANK CELL IS NOT A ZERO. It means no selected order owes that product by that date, so it
 * renders blank and stays blank.
 *
 * THE PAST IS TINTED ON ITS HEADER, NOT MERGED. Every dated bucket is a real date, however far
 * back, and the server's `is_past` is the only thing this grid colours a HEADER on. The board
 * used to carry one aggregate Overdue column and it collapsed a whole selection into it - 160 of
 * 160 lines, with their dates gone. The cost of the change is columns, and the board pays it: it
 * spans years, so the horizontal scroll below is load-bearing rather than a nicety.
 */
export function FulfilmentBoardMatrix({
  dateBuckets,
  rows,
  rowHeader,
  cells,
  draft,
  onOpenCell,
}: {
  dateBuckets: BoardDateBucket[];
  /** Whatever the vertical axis is: products, sales orders, customers or projects. */
  rows: BoardAxisRow[];
  /** What the corner cell calls them. */
  rowHeader: string;
  cells: BoardCell[];
  /**
   * THE panel's draft, not a set of keys derived from it: the cell counts what is ticked AND
   * colours itself by what was ticked, and two readings of one draft would drift.
   */
  draft: BoardDraft;
  onOpenCell: (cell: BoardCell) => void;
}) {
  // Keyed by the cell's ROW KEY, which is the item code on the product axis and an id on the
  // pivoted ones - two customers sharing a name must not share a row.
  const byKey = React.useMemo(() => {
    const map = new Map<string, BoardCell>();
    for (const cell of cells) {
      map.set(`${cell.row_key ?? cell.item_code}|${cell.bucket_key}`, cell);
    }
    return map;
  }, [cells]);

  return (
    <div
      data-testid="fulfilment-board-matrix"
      className="relative max-h-[70vh] w-full overflow-auto overscroll-x-contain rounded-lg border border-border"
    >
      <table className="w-full border-separate border-spacing-0 text-xs">
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
              {rowHeader}
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
          {rows.map((product) => (
            <tr key={product.key}>
              <th
                scope="row"
                className={cn(
                  PRODUCT_COL,
                  Z_PINNED,
                  'sticky left-0 border-b border-e border-border bg-background px-2 py-1.5 text-start font-medium',
                )}
              >
                {/* The label alone. A product's name is searchable but not printed here: the
                    first column is sticky and every character of it costs width on a board
                    that already spans years. */}
                <span className="block truncate" title={product.description || product.label}>
                  {product.label}
                </span>
              </th>

              {dateBuckets.map((bucket) => {
                const cell = byKey.get(`${product.key}|${bucket.key}`);
                return (
                  <td
                    key={bucket.key}
                    data-cell={`${product.key}|${bucket.key}`}
                    className={cn(DATE_COL, 'border-b border-e border-border p-0 align-top')}
                  >
                    {cell ? (
                      <BoardCellButton
                        cell={cell}
                        draft={draft}
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
  draft,
  onOpen,
}: {
  cell: BoardCell;
  draft: BoardDraft;
  onOpen: () => void;
}) {
  const decided = cell.contributions.filter((entry) => Boolean(draft[entry.key])).length;
  // Where this cell's quantity is coming from: the DECISION on every line that has one, the
  // engine's proposal on the rest. Ticking Amend from Buy to the shared pool flips the bar
  // rose to sky before anything is confirmed, and clearing the tick puts it back.
  const supply = cellSupply(cell, draft);
  const lead = dominant(supply.segments);
  // Only the locations this cell's own lines name. `cell.locations` also carries the rest of
  // the sales agent's ownership group, which holds none of this cell's demand - listing those
  // here would read "BRW-BB 42 · MWH-BB 0 · DC1-BB 0" on a grid whose whole job is to be
  // scanned. Their stock position is the drill-down's answer, not this strip's.
  const strip = cell.locations
    .filter((entry) => toMinor(entry.qty) > 0)
    .map((entry) => `${entry.location ?? 'No location'} ${entry.qty}`)
    .join(' · ');
  const orders = new Set(cell.contributions.map((entry) => entry.so_number)).size;
  // Confirmed in the DATABASE, not ticked in the draft: the `decided` badge below already
  // counts the draft, and a cell whose supply is settled is a different statement.
  const confirmedRevisions = decidedRevisions(cell.contributions);
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
      <span className="flex items-center gap-1.5">
        <span className="font-medium tabular-nums">{cell.total_qty}</span>
        <span className="text-[11px] text-muted-foreground">
          {orders === 1 ? '1 order' : `${orders} orders`}
        </span>
        <BoardDecidedMarker revisions={confirmedRevisions} />
      </span>

      {/* The source strip. One entry per distinct location, because one cell legitimately
          spans several: the location is the line's own, and lines from different orders do
          not have to agree about it (PLAN 13.7). */}
      <span className="block truncate text-[11px] text-muted-foreground" title={strip}>
        {strip}
      </span>

      {/* The supply bar, and the dominant kind in words under it. The words are there because
          a colour alone is not a label, and short because the column is 150px wide. */}
      <SupplyBar segments={supply.segments} decided={supply.decided} />
      {lead ? (
        <span
          data-testid="cell-supply-lead"
          className={cn('block truncate text-[11px] font-medium', COLOURS[lead.kind].text)}
        >
          {dominantText(supply.segments)}
        </span>
      ) : null}

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
