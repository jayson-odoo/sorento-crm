'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import { SoLinesDrillPopover } from './SoLinesDrillPopover';
import type {
  ContainerRequestMatrixBucket,
  ContainerRequestMatrixCell,
  ContainerRequestMatrixRow,
} from './containerRequestMatrix';

const ROW_COL = 'w-[220px] min-w-[220px] max-w-[220px]';
/** A floor, not a fixed width - `table-layout` is never `table-fixed` here, so a narrow
 *  selection fills the bordered container and a wide one overflows into its own scroll,
 *  mirroring `OrderInquiryScheduleMatrix`'s own reasoning for the same shape of table. */
const BUCKET_COL = 'min-w-[110px]';
const Z_PINNED = 'z-20';
const Z_CORNER = 'z-30';

/**
 * Ms Tee's schedule view of the request (6b.2): the product/SO axis and day/week/month
 * bucketing the captain asked for, reused here over the request's own `lines`. Modelled
 * wholesale on `OrderInquiryScheduleMatrix` (sticky first column, sticky header row, the whole
 * table scrolling inside THIS container rather than the page) - mirrored rather than imported
 * because the underlying row shape (a container-request SO line: no verb, no agent, no money)
 * is a different domain to the order-inquiry worklist row that component is built on.
 *
 * A BLANK CELL IS NOT A ZERO: no line in this selection lands on that row and bucket.
 *
 * Each cell IS its own drill trigger (`SoLinesDrillPopover`) rather than a click handler lifted
 * to a parent's `openCell` state - the same popover component the Open SOs column drill uses,
 * so a cell's own `lines` are exactly what its popover shows: no second idea of "what is in
 * this cell".
 */
export function ContainerRequestScheduleMatrix({
  buckets,
  rows,
  rowHeader,
  cells,
}: {
  buckets: ContainerRequestMatrixBucket[];
  rows: ContainerRequestMatrixRow[];
  rowHeader: string;
  cells: ContainerRequestMatrixCell[];
}) {
  const byKey = React.useMemo(() => {
    const map = new Map<string, ContainerRequestMatrixCell>();
    for (const cell of cells) map.set(`${cell.row_key}|${cell.bucket_key}`, cell);
    return map;
  }, [cells]);

  return (
    <div
      data-testid="container-request-schedule-matrix"
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
                        <SoLinesDrillPopover
                          title={`${row.label} - ${bucket.label}`}
                          lines={cell.lines}
                          trigger={
                            <button
                              type="button"
                              className="flex w-full flex-col items-end gap-0.5 px-2 py-1.5 text-end hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                            >
                              <span className="font-medium tabular-nums">{fmtInt(cell.qty)}</span>
                              <span className="text-[11px] text-muted-foreground">
                                {cell.lines.length} line{cell.lines.length === 1 ? '' : 's'}
                              </span>
                            </button>
                          }
                        />
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

export default ContainerRequestScheduleMatrix;
