'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { useStockDebtCellQuery } from '../hooks/useStockDebtQuery';
import type {
  StockDebtDemandLine,
  StockDebtDemandStatus,
  StockDebtSupplyEvent,
  StockDebtSupplyKind,
} from '../types/stockDebt.types';

/**
 * The two tables behind one cell (R28, AC-S2-11): what is DUE in that month, and what
 * is HELD or ARRIVING for it - each with its assignments.
 *
 * Both are the system list (`PanelDataGrid`), so a reader gets the same table here as
 * on every other screen. The view never decides: the only press is Plan, which hands
 * the order to the board (R23).
 */

/**
 * The shared soft-pastel status palette (ADR 1d), paired with `STATUS_PILL_BASE` - the
 * shape `BoardDecisionPill` uses for the board's own verdicts. A local map rather than
 * `statusPillClass`, for the same reason that pill keeps one: these four words are this
 * screen's vocabulary, and the shared map is keyed on form/document statuses that mean
 * something else. What is shared is the LOOK, so a status here and a status on the board
 * read as the same kind of thing.
 */
const STATUS_CLASS: Record<StockDebtDemandStatus, string> = {
  covered: 'bg-emerald-100 text-emerald-800',
  pinned: 'bg-sky-100 text-sky-800',
  late: 'bg-amber-100 text-amber-800',
  short: 'bg-red-100 text-red-800',
};

const KIND_LABEL: Record<StockDebtSupplyKind, string> = {
  on_hand: 'On hand',
  spo: 'SPO',
  po: 'PO',
};

function date(value: string | null): string {
  return value ? formatDateInMalaysia(value) : '-';
}

export function StockDebtCellDialog({
  productId,
  productCode,
  productName,
  month,
  monthLabel,
  balance,
  group,
  onClose,
}: {
  productId: string;
  productCode: string;
  productName: string | null;
  /** `YYYY-MM`, `tba`, `undated` or `unlocated`. */
  month: string;
  /** What the column header said, so the dialog names the same thing the reader clicked. */
  monthLabel: string;
  balance: number;
  /** The group the board is narrowed to, echoed so the figures are not read as the whole book. */
  group: string;
  onClose: () => void;
}) {
  // The board's own narrowing travels with the request AND with the cache key: the same
  // product and month answer differently under `group=BB`, so the drill has to be
  // recomputed over the span the cell that opened it was.
  const cell = useStockDebtCellQuery(productId, month, group);

  const demandColumns = React.useMemo<ColumnDef<StockDebtDemandLine>[]>(
    () => [
      {
        id: 'so_number',
        header: 'Sales order',
        size: 130,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.so_number}>
            {row.original.so_number}
          </span>
        ),
      },
      {
        id: 'agent_code',
        header: 'Agent',
        size: 110,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.agent_code ?? ''}>
            {row.original.agent_code ?? '-'}
          </span>
        ),
      },
      {
        // Before the date, because "which bin" is what decides whether this line and the
        // supply beside it are even the same pile (the ownership group is the code's suffix).
        id: 'warehouse_code',
        header: 'Bin',
        size: 110,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.warehouse_code ?? ''}>
            {row.original.warehouse_code ?? '-'}
          </span>
        ),
      },
      {
        id: 'required_date',
        header: 'Due',
        size: 120,
        cell: ({ row }) => <span>{date(row.original.required_date)}</span>,
      },
      {
        id: 'open_qty',
        header: 'Open',
        size: 90,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.open_qty.toLocaleString()}</span>
        ),
      },
      {
        id: 'assigned_qty',
        header: 'Assigned',
        size: 100,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.assigned_qty.toLocaleString()}</span>
        ),
      },
      {
        id: 'assigned_source',
        header: 'From',
        size: 190,
        cell: ({ row }) => (
          <span
            className="block truncate text-muted-foreground"
            title={row.original.assigned_source ?? 'Nothing assigned'}
          >
            {row.original.assigned_source ?? 'Nothing assigned'}
          </span>
        ),
      },
      {
        id: 'status',
        header: 'Status',
        size: 120,
        cell: ({ row }) => {
          const shortfall = row.original.open_qty - row.original.assigned_qty;
          const label =
            row.original.status === 'short' && shortfall > 0
              ? `short ${shortfall.toLocaleString()}`
              : row.original.status;
          return (
            <span className={cn(STATUS_PILL_BASE, STATUS_CLASS[row.original.status])}>
              {label}
            </span>
          );
        },
      },
      {
        id: 'plan',
        header: '',
        size: 90,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button variant="outline" size="sm" asChild>
              <Link
                href={`/project-sales/fulfilment-planning?orders=${encodeURIComponent(
                  row.original.so_number,
                )}`}
              >
                Plan
              </Link>
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const supplyColumns = React.useMemo<ColumnDef<StockDebtSupplyEvent>[]>(
    () => [
      {
        id: 'kind',
        header: 'Kind',
        size: 90,
        cell: ({ row }) => <span>{KIND_LABEL[row.original.kind]}</span>,
      },
      {
        id: 'ref',
        header: 'Document',
        size: 190,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.ref ?? ''}>
            {row.original.ref ?? '-'}
          </span>
        ),
      },
      {
        id: 'warehouse_code',
        header: 'Bin',
        size: 110,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.warehouse_code ?? ''}>
            {row.original.warehouse_code ?? '-'}
          </span>
        ),
      },
      {
        id: 'date',
        header: 'Arrival',
        size: 120,
        cell: ({ row }) => <span>{date(row.original.date)}</span>,
      },
      {
        id: 'qty',
        header: 'Qty',
        size: 90,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.qty.toLocaleString()}</span>
        ),
      },
      {
        id: 'assigned_to',
        header: 'Assigned to',
        size: 190,
        cell: ({ row }) => {
          const label = row.original.assigned_to.length
            ? row.original.assigned_to
                .map((entry) => `${entry.so_number} (${entry.qty.toLocaleString()})`)
                .join(', ')
            : 'Free';
          return (
            <span className="block truncate text-muted-foreground" title={label}>
              {label}
            </span>
          );
        },
      },
      {
        id: 'note',
        header: 'Note',
        size: 230,
        cell: ({ row }) => {
          // A PO line's `expected_date` is the SO date it was TYPED against, not an
          // arrival (R29), so it is stated as what it is and nothing reads it (R30).
          const boughtFor =
            row.original.kind === 'po' && row.original.bought_for
              ? `bought for ${date(row.original.bought_for)}`
              : null;
          return (
            <div className="flex min-w-0 items-center gap-2">
              {row.original.overdue && (
                <span
                  className={cn(
                    STATUS_PILL_BASE,
                    'shrink-0 normal-case',
                    'bg-amber-100 text-amber-800',
                  )}
                >
                  overdue, not counted
                </span>
              )}
              {boughtFor && (
                <span className="truncate text-muted-foreground" title={boughtFor}>
                  {boughtFor}
                </span>
              )}
              {!row.original.overdue && !boughtFor && (
                <span className="text-muted-foreground">-</span>
              )}
            </div>
          );
        },
      },
    ],
    [],
  );

  const signedBalance = balance > 0 ? `+${balance.toLocaleString()}` : balance.toLocaleString();

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      {/* Capped and scrolling in its BODY, so two grids and their pagination bars stay
          reachable at a short window - the same layout contract the board's cell dialog
          carries. `sm:max-w-[95vw]` because seven columns need the width. */}
      <DialogContent
        data-testid="stock-debt-cell-dialog"
        className="flex max-h-[90vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]"
      >
        <DialogHeader className="shrink-0 space-y-2 border-b p-4 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle className="min-w-0 break-words">
              {productName
                ? `${productCode} - ${productName} · ${monthLabel}`
                : `${productCode} · ${monthLabel}`}
            </DialogTitle>
            <Badge
              variant="outline"
              className={cn(
                balance < 0
                  ? 'border-destructive/40 bg-destructive/10 text-destructive'
                  : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
              )}
            >
              {`balance ${signedBalance}`}
            </Badge>
            {group && <Badge variant="outline">{`${group} group`}</Badge>}
          </div>
        </DialogHeader>

        <DialogBody className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
          {cell.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <>
              <PanelDataGrid<StockDebtDemandLine>
                title="Demand"
                columns={demandColumns}
                rows={cell.data?.demand ?? []}
                listingKey="projects.stock_debt.view::cell-demand"
                error={cell.error}
                emptyTitle="Nothing is due here"
                emptyBody="No sales order line falls in this column."
                pageSize={10}
              />
              <PanelDataGrid<StockDebtSupplyEvent>
                title="Supply"
                columns={supplyColumns}
                rows={cell.data?.supply ?? []}
                listingKey="projects.stock_debt.view::cell-supply"
                error={cell.error}
                emptyTitle="Nothing arrives here"
                emptyBody="No stock is held or on the way for this column."
                pageSize={10}
              />
            </>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
