'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
 * ONE lightbox for the SCM family: the shell (sizing, header layout, scrolling body) is
 * COPIED from `scm/components/PlanRowDialog.tsx`, exactly the way that file copied it from
 * the reorder lane's `PlanRowDialogs.tsx` - the same object to a reader, with none of that
 * module's six data hooks dragged into this page's bundle for twenty lines of frame. At
 * whichever merge lands last, the three re-point at one file (plan section 9).
 *
 * Demand and Supply are TABS, like `ProjectRetailTabs` next door: two stacked grids made
 * the reader scroll past one to reach the other, and the counts belong in the trigger where
 * they can be read without opening anything.
 *
 * Both are the system list (`PanelDataGrid`), so a reader gets the same table here as
 * on every other screen. The view never decides: the only press is Plan, which hands
 * the order to the board (R23).
 *
 * Each tab foots with the cell that opened it (R37): `Free` less `Uncovered` IS the
 * balance in the title, because a month states its own month and nothing carries into it.
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
          // `short_qty` is the SERVER's own figure - what the line went without ON ITS OWN
          // DATE (R37), which is also what its month books and what the footer below sums.
          // Re-deriving it as `open - assigned` disagreed with the payload the moment later
          // supply cleared the shortfall: a `late` line ended fully assigned and printed
          // "short 0" beside a cell the same line had put in debt.
          //
          // A LATE line is exactly that case - later supply cleared it, so Open and Assigned
          // read the same - and it STILL books its shortfall in this month (R37, AC-S2-7).
          // Printing only the word "late" left the figure the cell was made of unsaid, so
          // the row is stated as `late . short 40`: what happened, and how much of it.
          const { status, short_qty: shortQty } = row.original;
          const pill = cn(STATUS_PILL_BASE, STATUS_CLASS[status]);
          const shortLabel = `short ${shortQty.toLocaleString()}`;
          if (shortQty > 0 && status === 'short') {
            // "short 16" already says both, so the word is not repeated.
            return <span className={pill}>{shortLabel}</span>;
          }
          if (shortQty > 0 && status === 'late') {
            return (
              <span className={cn(pill, 'gap-1')}>
                {status}
                <span aria-hidden="true">&middot;</span>
                <span>{shortLabel}</span>
              </span>
            );
          }
          return <span className={pill}>{status}</span>;
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

  const demand = cell.data?.demand ?? [];
  const supply = cell.data?.supply ?? [];
  const signedBalance = balance > 0 ? `+${balance.toLocaleString()}` : balance.toLocaleString();
  // The two halves of the cell (R37), summed here rather than on the server: the rows ARE
  // the month, so a reader can add the column up and land on the balance in the title.
  const uncovered = demand.reduce((total, row) => total + row.short_qty, 0);
  const free = supply.reduce((total, row) => total + row.free_qty, 0);
  const context = [monthLabel, signedBalance, group ? `${group} group` : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      {/* The SCM family's shell, copied from `scm/components/PlanRowDialog.tsx`: same
          sizing, same header, same scrolling body, so the two screens' lightboxes are one
          object to a reader. */}
      <DialogContent
        data-testid="stock-debt-cell-dialog"
        className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]"
      >
        {/* `pe-10` is the one departure from the copied shell: the close button is absolute
            at `end-5`, and at 375px the month and the balance ran underneath it. */}
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 pe-10 sm:p-6 sm:pe-10">
          <DialogTitle className="min-w-0 break-words">
            {`Product · ${productCode}`}
            <span className="ms-2 text-xs font-normal text-muted-foreground">{context}</span>
          </DialogTitle>
          <DialogDescription className="truncate text-xs" title={productName ?? undefined}>
            {productName ?? productCode}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {cell.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <Tabs defaultValue="demand">
              <TabsList>
                <TabsTrigger value="demand">{`Demand (${demand.length})`}</TabsTrigger>
                <TabsTrigger value="supply">{`Supply (${supply.length})`}</TabsTrigger>
              </TabsList>

              <TabsContent value="demand">
                <PanelDataGrid<StockDebtDemandLine>
                  title="Demand"
                  columns={demandColumns}
                  rows={demand}
                  listingKey="projects.stock_debt.view::cell-demand"
                  error={cell.error}
                  emptyTitle="Nothing is due here"
                  emptyBody="No sales order line falls in this column."
                  pageSize={10}
                />
                <p className="mt-2 border-t pt-2 text-2xs text-muted-foreground">
                  {`Uncovered ${uncovered.toLocaleString()}`}
                </p>
              </TabsContent>

              <TabsContent value="supply">
                <PanelDataGrid<StockDebtSupplyEvent>
                  title="Supply"
                  columns={supplyColumns}
                  rows={supply}
                  listingKey="projects.stock_debt.view::cell-supply"
                  error={cell.error}
                  emptyTitle="Nothing arrives here"
                  emptyBody="No stock is held or on the way for this column."
                  pageSize={10}
                />
                <p className="mt-2 border-t pt-2 text-2xs text-muted-foreground">
                  {`Free ${free.toLocaleString()}`}
                </p>
              </TabsContent>
            </Tabs>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
