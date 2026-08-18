'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { PackageSearch } from 'lucide-react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { usePileQueue } from '../../_shared/hooks/useFulfilmentPlanning';
import { aheadFactorLabel } from '../../_shared/lib/fulfilmentBoard';
import type { PileQueueLine } from '../../_shared/types/fulfilmentPlanning.types';
import { BoardRankPopover } from './BoardRankPopover';

/**
 * The whole queue at one pile, in the order the stock is actually served.
 *
 * The captain, having been given the top three beside the rung: "I need to know what is ahead of
 * me to have the visibility, and why they are ahead of me, meaning I need to know their rank
 * also."
 *
 * So this is the queue in full: every line still competing for this product at this location,
 * ranked, with the running total of what is claimed by the time the queue reaches each one - so
 * the row where the pile runs out is visible by eye rather than by arithmetic. The asking line
 * is marked and the rows BEHIND it are dimmed, because they are not the answer to "why did I get
 * nothing": everybody above the mark is.
 *
 * The Score column opens the same rank popover a board row carries, so one line's factor table
 * is one press away and the two screens can never explain a rank differently.
 */
export function PileQueueDialog({
  productId,
  warehouseId,
  lineId,
  itemCode,
  onClose,
}: {
  productId: string;
  warehouseId: string;
  /** The CORE line asking. Its row is marked and every row above it says why it is above. */
  lineId?: string | null;
  itemCode: string;
  onClose: () => void;
}) {
  const queue = usePileQueue(productId, warehouseId, lineId);
  const data = queue.data;
  const rows = data?.lines ?? [];
  const position = data?.this_line_position ?? null;

  const columns = React.useMemo<ColumnDef<PileQueueLine>[]>(
    () => [
      {
        id: 'position',
        accessorFn: (row) => row.position,
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => (
          <span
            className={cellClass(row.original, position)}
            {...(row.original.is_this_line ? { 'data-testid': 'queue-this-line' } : {})}
          >
            {row.original.is_this_line
              ? `${row.original.position} (this line)`
              : row.original.position}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: '#' },
      },
      {
        id: 'so_number',
        accessorFn: (row) => row.so_number,
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) =>
          row.original.sales_order_id ? (
            <Link
              href={`/scm/sales-orders/${row.original.sales_order_id}`}
              className={`${cellClass(row.original, position)} text-primary hover:underline`}
              title={row.original.so_number}
            >
              {row.original.so_number}
            </Link>
          ) : (
            <span className={cellClass(row.original, position)} title={row.original.so_number}>
              {row.original.so_number}
            </span>
          ),
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Sales order' },
      },
      {
        id: 'line_no',
        accessorFn: (row) => row.line_no ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Line" column={column} />,
        cell: ({ row }) => (
          <span className={cellClass(row.original, position)}>
            {row.original.line_no ?? 'Not planned'}
          </span>
        ),
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Line' },
      },
      {
        id: 'customer_name',
        accessorFn: (row) => row.customer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => (
          <span
            className={cellClass(row.original, position)}
            title={row.original.customer_name ?? ''}
          >
            {row.original.customer_name || 'Not recorded'}
          </span>
        ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Customer' },
      },
      {
        id: 'qty',
        accessorFn: (row) => Number(row.qty || 0),
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className={`${cellClass(row.original, position)} tabular-nums`}>
            {row.original.qty}
          </span>
        ),
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Qty' },
      },
      {
        id: 'cumulative_ahead_qty',
        accessorFn: (row) => Number(row.cumulative_ahead_qty || 0),
        header: ({ column }) => <DataGridColumnHeader title="Cumulative" column={column} />,
        cell: ({ row }) => (
          <span className={`${cellClass(row.original, position)} tabular-nums`}>
            {row.original.cumulative_ahead_qty}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Cumulative' },
      },
      {
        id: 'required_date',
        accessorFn: (row) => row.required_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Required" column={column} />,
        cell: ({ row }) => (
          <span className={`${cellClass(row.original, position)} tabular-nums`}>
            {row.original.required_date
              ? formatDateInMalaysia(row.original.required_date)
              : 'Not stated'}
          </span>
        ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Required' },
      },
      {
        id: 'order_date',
        accessorFn: (row) => row.order_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Order date" column={column} />,
        cell: ({ row }) => (
          <span className={`${cellClass(row.original, position)} tabular-nums`}>
            {row.original.order_date
              ? formatDateInMalaysia(row.original.order_date)
              : 'Not stated'}
          </span>
        ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Order date' },
      },
      {
        id: 'payment_terms_days',
        accessorFn: (row) => row.payment_terms_days ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="Terms" column={column} />,
        cell: ({ row }) => (
          <span className={`${cellClass(row.original, position)} tabular-nums`}>
            {row.original.payment_terms_days === null ||
            row.original.payment_terms_days === undefined
              ? 'Not assessed'
              : `${row.original.payment_terms_days} days`}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Terms' },
      },
      {
        id: 'rank_score',
        accessorFn: (row) => row.rank_score,
        header: ({ column }) => <DataGridColumnHeader title="Score" column={column} />,
        cell: ({ row }) => (
          <span className="flex items-center gap-1">
            <span className={`${cellClass(row.original, position)} tabular-nums`}>
              {row.original.rank_score.toFixed(2)}
            </span>
            <BoardRankPopover
              contribution={{
                key: row.original.line_id,
                rank_factors: row.original.rank_factors,
              }}
              policyName={data?.policy_name}
            />
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Score' },
      },
      {
        id: 'leading_factor',
        accessorFn: (row) => row.leading_factor ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Ahead because" column={column} />,
        cell: ({ row }) => (
          <span className={cellClass(row.original, position)}>
            {row.original.is_this_line
              ? 'This line'
              : row.original.leading_factor
                ? aheadFactorLabel(row.original.leading_factor)
                : behindLabel(row.original, position)}
          </span>
        ),
        size: 160,
        minSize: 130,
        enableSorting: false,
        meta: { headerTitle: 'Ahead because' },
      },
    ],
    [position, data?.policy_name],
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="shrink-0 border-b p-4 sm:p-6">
          <DialogTitle>{`Who is ahead of this line for ${itemCode}`}</DialogTitle>
          {/* The pile, what it held, and where this line stands in the queue for it. Stated
              once, at the top, so every row below is read against the same three facts. */}
          <DialogDescription
            data-testid="queue-header-line"
            className="min-w-0 break-words text-sm text-muted-foreground tabular-nums"
          >
            {data
              ? [
                  data.location,
                  `${data.qty_free_opening} free at opening`,
                  position
                    ? `this line is #${position} of ${data.lines.length}`
                    : `${data.lines.length} lines in the queue`,
                ].join(' · ')
              : 'Loading the queue'}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 sm:p-6">
          {queue.isError ? (
            <p className="py-6 text-center text-sm text-destructive">
              {queue.error instanceof Error
                ? queue.error.message
                : 'The queue could not be loaded.'}
            </p>
          ) : queue.isLoading ? (
            <div data-testid="queue-loading" className="space-y-2 py-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : rows.length === 0 ? (
            <div className="py-8 text-center">
              <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
              <h3 className="mt-2 text-sm font-semibold">Nothing is queuing for this stock</h3>
            </div>
          ) : (
            <>
              <PanelDataGrid<PileQueueLine>
                title={`Ranked by ${data?.policy_name ?? 'the active policy'}`}
                columns={columns}
                rows={rows}
                getRowId={(row) => row.line_id}
                listingKey="projects.projects.view::project-pile-queue"
                emptyTitle="Nothing is queuing for this stock"
                searchPlaceholder="Search sales order or customer"
                searchOf={(row) => `${row.so_number} ${row.customer_name ?? ''}`}
                // The widest pile on the live book is 289 lines. Paging it would hide the row
                // where the running total passes what the pile holds, which is the one row the
                // reader came for.
                pageSize={500}
              />
              {/* Said once, at the bottom, because it is a fact about the QUEUE rather than
                  about any row: a line a confirmed decision covers is not in it. */}
              <p className="text-xs text-muted-foreground">
                Lines a confirmed decision already covers are not in this queue.
              </p>
            </>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The asking line is marked, and everything BEHIND it is dimmed.
 *
 * The question is "who is ahead of me", so the rows that answer it are the ones above the mark.
 * Dimming the rest keeps them readable - they are still the rest of the queue - without letting
 * them compete for attention with the part that is the answer.
 */
function cellClass(row: PileQueueLine, position: number | null): string {
  const base = 'block truncate text-sm';
  if (row.is_this_line) return `${base} font-semibold text-primary`;
  if (position !== null && row.position > position) return `${base} text-muted-foreground/60`;
  return base;
}

/** A row BEHIND the asking line is not ahead of it, and must not claim to be. */
function behindLabel(row: PileQueueLine, position: number | null): string {
  if (position !== null && row.position > position) return 'Behind this line';
  return '-';
}

export default PileQueueDialog;
