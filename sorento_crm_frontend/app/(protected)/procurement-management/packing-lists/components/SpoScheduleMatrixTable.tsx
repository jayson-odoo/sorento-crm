'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
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
 */
export function SpoScheduleMatrixTable<T>({
  rowHeader,
  rows,
  buckets,
  cells,
  renderDrill,
}: {
  rowHeader: string;
  rows: SpoMatrixRow[];
  buckets: SpoMatrixBucket[];
  cells: SpoMatrixCell<T>[];
  renderDrill: (cell: SpoMatrixCell<T>, label: string) => React.ReactNode;
}) {
  const byKey = React.useMemo(() => {
    const map = new Map<string, SpoMatrixCell<T>>();
    for (const cell of cells) map.set(`${cell.row_key}|${cell.bucket_key}`, cell);
    return map;
  }, [cells]);

  return (
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
                  return (
                    <td
                      key={bucket.key}
                      data-cell={`${row.key}|${bucket.key}`}
                      className="border-b border-e border-border p-0 align-top"
                    >
                      {cell ? (
                        <Popover>
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              className="flex w-full flex-col items-end gap-0.5 px-2 py-1.5 text-end hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                            >
                              <span className="font-medium tabular-nums">{fmtInt(cell.qty)}</span>
                              <span className="text-[11px] text-muted-foreground">
                                {cell.entries.length} line{cell.entries.length === 1 ? '' : 's'}
                              </span>
                            </button>
                          </PopoverTrigger>
                          <PopoverPortal>
                            <PopoverContent align="start" className="w-80 space-y-2 p-3">
                              {renderDrill(cell, `${row.label} - ${bucket.label}`)}
                            </PopoverContent>
                          </PopoverPortal>
                        </Popover>
                      ) : null}
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
  );
}

export default SpoScheduleMatrixTable;
