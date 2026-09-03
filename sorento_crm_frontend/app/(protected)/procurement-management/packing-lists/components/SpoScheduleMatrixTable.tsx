'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import type { SpoMatrixBucket, SpoMatrixCell, SpoMatrixRow } from './spoScheduleMatrix';

const ROW_COL = 'w-[220px] min-w-[220px] max-w-[220px]';
const BUCKET_COL = 'min-w-[110px]';
const Z_PINNED = 'z-(--z-sticky-content)';
const Z_CORNER = 'z-(--z-sticky-content-corner)';
const EM_DASH = '-';
const intFmt = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return intFmt.format(value);
}

/**
 * The table shell BOTH SPO schedule views share (doctrine correction, captain's ask #3) - the
 * PO-coverage matrix and the SO-coverage matrix are the same "product row x weekly bucket"
 * shape with a different drill inside each cell, so the shell (sticky column, sticky header,
 * row totals, own scroll container) lives once here - mirrored on `ContainerRequestScheduleMatrix`
 * (the loading plan's own precedent), not imported: that component's drill is typed to a
 * container-request SO line, a different shape to either of this planner's two entry types.
 *
 * A BLANK CELL IS NOT A ZERO: nothing in this selection lands on that row and bucket.
 *
 * S4 (schedule cells, captain's feedback round): the hover `Popover` is gone. A cell is now a
 * plain `button`, and clicking it (or Enter/Space, being a button, for free) hands the caller
 * the CELL and the BUCKET; the caller decides what "the same lightbox" means (`kind='po_takes'`
 * in the Purchase order view, `kind='so_coverage'` in the Sales order view - `SpoPlannerTable`
 * owns that decision, not this shell). A colour with no key is a guess the reader has to make,
 * so the legend renders every time this component mounts (schedule view only, by construction:
 * nothing else renders it).
 */
export function SpoScheduleMatrixTable<T>({
  rowHeader,
  rows,
  buckets,
  cells,
  onCellClick,
}: {
  rowHeader: string;
  rows: SpoMatrixRow[];
  buckets: SpoMatrixBucket[];
  cells: SpoMatrixCell<T>[];
  onCellClick: (cell: SpoMatrixCell<T>, bucket: SpoMatrixBucket) => void;
}) {
  const byKey = React.useMemo(() => {
    const map = new Map<string, SpoMatrixCell<T>>();
    for (const cell of cells) map.set(`${cell.row_key}|${cell.bucket_key}`, cell);
    return map;
  }, [cells]);

  return (
    <div className="space-y-2">
      <div
        data-testid="spo-schedule-matrix"
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
              <th
                scope="col"
                className={cn(
                  Z_PINNED,
                  'sticky top-0 min-w-[90px] border-b border-border bg-muted px-2 py-2 text-end align-bottom font-medium',
                )}
              >
                Total
              </th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => {
              const rowTotal = buckets.reduce(
                (sum, bucket) => sum + (byKey.get(`${row.key}|${bucket.key}`)?.qty ?? 0),
                0,
              );
              return (
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
                    {row.description ? (
                      <span className="block truncate text-2xs font-normal text-muted-foreground" title={row.description}>
                        {row.description}
                      </span>
                    ) : null}
                  </th>

                  {buckets.map((bucket) => {
                    const cell = byKey.get(`${row.key}|${bucket.key}`);
                    if (!cell) {
                      return (
                        <td
                          key={bucket.key}
                          data-cell={`${row.key}|${bucket.key}`}
                          className="border-b border-e border-border p-0 align-top"
                        >
                          {null}
                        </td>
                      );
                    }
                    // AC-D1/AC-E8: this SPO's own take tints the cell and bolds the figure;
                    // a cell occupied ONLY by another SPO is muted; a cell with both keeps
                    // the tint (it is still this SPO's cell) and adds a second, muted line
                    // for what else sits on the same date.
                    const hasQty = cell.qty > 0;
                    const hasTaken = cell.taken_qty > 0;
                    return (
                      <td
                        key={bucket.key}
                        data-cell={`${row.key}|${bucket.key}`}
                        className="border-b border-e border-border p-0 align-top"
                      >
                        <button
                          type="button"
                          aria-label={`${row.label} - ${bucket.label}`}
                          onClick={() => onCellClick(cell, bucket)}
                          className={cn(
                            'flex w-full flex-col items-end gap-0.5 px-2 py-1.5 text-end hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
                            hasQty && 'bg-primary/10',
                            !hasQty && hasTaken && 'bg-muted text-muted-foreground',
                          )}
                        >
                          <span className={cn('tabular-nums', hasQty && 'font-semibold')}>
                            {fmtInt(hasQty ? cell.qty : cell.taken_qty)}
                          </span>
                          {hasQty && hasTaken ? (
                            // S5: the FIRST SPO number behind `taken_qty`, "first if several"
                            // (the plan's own words) - a name reads faster than a count, and
                            // the picker this cell opens still lists every one of them.
                            <span className="text-[11px] text-muted-foreground">
                              {cell.taken_by[0]
                                ? `+${fmtInt(cell.taken_qty)} on ${cell.taken_by[0]}`
                                : `+${fmtInt(cell.taken_qty)} other SPO`}
                            </span>
                          ) : hasQty ? (
                            <span className="text-[11px] text-muted-foreground">
                              {cell.entries.length} line{cell.entries.length === 1 ? '' : 's'}
                            </span>
                          ) : null}
                        </button>
                      </td>
                    );
                  })}
                  <td className="border-b border-border px-2 py-1.5 text-end font-medium tabular-nums">
                    {rowTotal > 0 ? fmtInt(rowTotal) : EM_DASH}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AC-D5: a colour with no key is a guess, so this renders every time the matrix does -
          schedule view only, by construction (only this component mounts it). */}
      <div
        data-testid="spo-schedule-legend"
        className="flex flex-wrap items-center gap-x-4 gap-y-1 px-2 py-1.5 text-2xs text-muted-foreground"
      >
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm border border-primary/30 bg-primary/10" aria-hidden />
          This SPO
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm border border-border bg-muted" aria-hidden />
          Taken elsewhere
        </span>
      </div>
    </div>
  );
}

export default SpoScheduleMatrixTable;
