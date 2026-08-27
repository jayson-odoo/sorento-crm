'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { DocTable, EmptyRow, Td, Th } from '../../components/PlanRowDialog';
import { EM_DASH, fmtInt } from '../../lib/format';
import type { ContainerRequestSoLine } from '../../services/fulfilmentService';
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
 * A cell opens the lines behind it in a dialog, the same object the eight grid figures open
 * (R7). It was a hover popover until S2, pinned to `document.body` to escape this table's own
 * sticky columns; the lines it lists are a document table, which is what a dialog is for.
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

  // The cell whose lines are open. One state for the whole matrix: two cells cannot be open
  // at once, and the lines are the cell's own, so there is no second idea of what is in it.
  const [openCell, setOpenCell] = React.useState<{
    title: string;
    lines: ContainerRequestSoLine[];
  } | null>(null);

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
                        <button
                          type="button"
                          title={`${row.label} - ${bucket.label}`}
                          onClick={() => setOpenCell({ title: `${row.label} · ${bucket.label}`, lines: cell.lines })}
                          className="flex w-full flex-col items-end gap-0.5 px-2 py-1.5 text-end hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                        >
                          <span className="font-medium tabular-nums">{fmtInt(cell.qty)}</span>
                          <span className="text-[11px] text-muted-foreground">
                            {cell.lines.length} line{cell.lines.length === 1 ? '' : 's'}
                          </span>
                        </button>
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

      {openCell ? (
        <Dialog open onOpenChange={(next) => (next ? null : setOpenCell(null))}>
          <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]">
            <DialogHeader className="shrink-0 space-y-1 border-b p-4 sm:p-6">
              <DialogTitle className="min-w-0 break-words">{openCell.title}</DialogTitle>
              <DialogDescription className="text-xs">
                {`${fmtInt(openCell.lines.length)} SO line${openCell.lines.length === 1 ? '' : 's'}`}
              </DialogDescription>
            </DialogHeader>
            <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
              <DocTable>
                <thead>
                  <tr className="border-b">
                    <Th>Sales order</Th>
                    <Th>Customer</Th>
                    <Th>Class</Th>
                    <Th right>Ordered</Th>
                    <Th right>Qty</Th>
                    <Th right>Needed</Th>
                  </tr>
                </thead>
                <tbody>
                  {openCell.lines.length === 0 ? (
                    <EmptyRow colSpan={6}>No lines here.</EmptyRow>
                  ) : (
                    openCell.lines.map((l, i) => (
                      <tr
                        key={`${l.so_number ?? 'unnumbered'}-${i}`}
                        className="border-b last:border-0"
                      >
                        <Td>{l.so_number ?? 'Not numbered'}</Td>
                        <Td title={l.customer_label ?? undefined}>
                          <span className="block max-w-56 truncate">
                            {l.customer_label ?? EM_DASH}
                          </span>
                        </Td>
                        <Td>{classLabel(l.demand_class)}</Td>
                        <Td right>
                          {l.order_date ? formatDateInMalaysia(l.order_date) : EM_DASH}
                        </Td>
                        <Td right>{fmtInt(l.qty)}</Td>
                        <Td right>
                          {l.required_date ? formatDateInMalaysia(l.required_date) : EM_DASH}
                        </Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </DocTable>
            </DialogBody>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  );
}

/** An unclassified line is named as such, never quietly counted as retail. */
function classLabel(demandClass: string | null): string {
  if (demandClass === 'project') return 'Project';
  if (demandClass) return 'Retail';
  return 'Unclassified';
}

export default ContainerRequestScheduleMatrix;
