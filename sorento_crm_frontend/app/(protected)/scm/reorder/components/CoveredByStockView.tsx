'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt, fmtMoney } from '../../lib/format';
import { decideCoveredRow } from '../services/reorderRunService';
import { todayRunKey } from '../hooks/useReorderRun';
import { PlanDemandPopover } from './PlanDemandPopover';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * Demand the location's own stock already covers.
 *
 * The engine used to write nothing for these, which meant it had quietly decided "use
 * stock" on the planner's behalf. CS has already filtered what needs buying against what
 * the branch holds, so a line reaching the plan is a real requirement; finding stock in the
 * pool is worth saying, and is not the engine's decision to take.
 *
 * A decided row STAYS here, wearing its decision. It used to vanish on "Buy anyway", which
 * left the planner with no way to see what they had chosen and no way to change it - and
 * "Use stock" changed nothing visible at all, so the click read as broken.
 *
 * Same DataGrid every other listing uses: server-consistent search, resizable columns, a
 * header that stays put while the body scrolls.
 */

/** Shares `/scm/reorder` with the other grids; an empty key opts out of persistence. */
const NO_COLUMN_PERSISTENCE = '';

const numMeta = { headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' };

type Decision = 'use_stock' | 'buy' | 'pending';

/** What the row's `decision_status` means to a reader. `proposed` = nobody has decided. */
function decisionOf(r: ReorderRecommendation): Decision {
  const s = r.decision_status;
  if (s === 'use_stock') return 'use_stock';
  if (s === 'buy') return 'buy';
  return 'pending';
}

const DECISION_LABEL: Record<Decision, string> = {
  use_stock: 'Using stock',
  buy: 'Buying anyway',
  pending: 'Not decided',
};

export function CoveredByStockView({
  rows,
  isLoading,
  isError,
  error,
  runId,
}: {
  rows: ReorderRecommendation[];
  isLoading: boolean;
  isError?: boolean;
  error?: unknown;
  runId?: string | null;
}) {
  const qc = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  // Which row is mid-flight. Its controls disable together, so a second click cannot send
  // the opposite decision while the first is still in the air, and the spinner is the
  // feedback that something IS happening.
  const [pending, setPending] = useState<string | null>(null);
  // What the server has been told, before the refetch lands. Without it the row snaps back
  // to its old state for a beat and the click looks like it did nothing.
  const [optimistic, setOptimistic] = useState<Record<string, Decision>>({});

  const decide = useMutation({
    mutationFn: ({ id, choice }: { id: string; choice: Decision }) =>
      decideCoveredRow(id, choice),
    onMutate: ({ id, choice }) => {
      setPending(id);
      setOptimistic((m) => ({ ...m, [id]: choice }));
    },
    onSettled: () => setPending(null),
    onSuccess: (_res, { choice }) => {
      void qc.invalidateQueries({ queryKey: ['scm', 'reorder', 'covered-recs', runId] });
      void qc.invalidateQueries({ queryKey: todayRunKey });
      toast.success(
        choice === 'buy'
          ? 'Marked to buy anyway. It stays here so you can change it.'
          : choice === 'use_stock'
            ? 'Marked as covered by stock.'
            : 'Decision cleared.',
      );
    },
    onError: (e, { id }) => {
      // Put the row back the way it was: a failed write that leaves the optimistic state
      // on screen is a lie about what the server holds.
      setOptimistic((m) => {
        const next = { ...m };
        delete next[id];
        return next;
      });
      toast.error(e instanceof Error ? e.message : 'Failed to record the decision');
    },
  });

  const columns = useMemo<ColumnDef<ReorderRecommendation>[]>(
    () => [
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="SKU" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium" title={row.original.sku}>
                {row.original.sku}
              </span>
              {/* Which orders this committed figure is actually made of. */}
              <PlanDemandPopover runId={runId ?? null} recId={row.original.id} />
            </div>
            {/* The part of this demand nobody located: the part most likely to be wrong. */}
            {row.original.unlocated_demand ? (
              <Badge variant="secondary" size="sm" className="mt-0.5 font-normal">
                {fmtInt(row.original.unlocated_demand)} unlocated
              </Badge>
            ) : null}
          </div>
        ),
        size: 220,
        meta: { headerTitle: 'SKU' },
      },
      {
        accessorKey: 'warehouse_code',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => row.original.warehouse_code ?? EM_DASH,
        size: 120,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'committed',
        accessorFn: (r) => r.covered_committed ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Committed" column={column} />,
        cell: ({ row }) => fmtInt(row.original.covered_committed ?? null),
        size: 110,
        meta: { headerTitle: 'Committed', ...numMeta },
      },
      {
        id: 'available',
        accessorFn: (r) => r.covered_available ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Available" column={column} />,
        cell: ({ row }) => fmtInt(row.original.covered_available ?? null),
        size: 110,
        meta: { headerTitle: 'Available', ...numMeta },
      },
      {
        id: 'buy_qty',
        accessorFn: (r) => r.order_qty ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Buy anyway" column={column} />,
        cell: ({ row }) => fmtInt(row.original.order_qty),
        size: 110,
        meta: { headerTitle: 'Buy anyway', ...numMeta },
      },
      {
        id: 'cost',
        accessorFn: (r) => r.cash_impact ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Cost to buy" column={column} />,
        cell: ({ row }) =>
          row.original.cash_impact == null ? EM_DASH : fmtMoney(row.original.cash_impact),
        size: 130,
        meta: { headerTitle: 'Cost to buy', ...numMeta },
      },
      {
        id: 'decision',
        header: ({ column }) => <DataGridColumnHeader title="Decision" column={column} />,
        cell: ({ row }) => {
          const d = optimistic[row.original.id] ?? decisionOf(row.original);
          if (pending === row.original.id) {
            return (
              <span className="inline-flex items-center gap-1.5 text-2xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
                Saving
              </span>
            );
          }
          return (
            <span
              className={cn(
                STATUS_PILL_BASE,
                statusPillClass(
                  d === 'buy' ? 'submitted' : d === 'use_stock' ? 'closed' : 'draft',
                ),
              )}
            >
              {DECISION_LABEL[d]}
            </span>
          );
        },
        size: 140,
        meta: { headerTitle: 'Decision' },
      },
      {
        accessorKey: 'reason_label',
        header: ({ column }) => <DataGridColumnHeader title="Why it is here" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate text-2xs text-muted-foreground"
            title={row.original.reason_label ?? undefined}
          >
            {row.original.reason_label ?? EM_DASH}
          </span>
        ),
        size: 280,
        meta: { headerTitle: 'Why it is here' },
      },
      {
        id: 'actions',
        header: () => <span className="text-end">Decide</span>,
        cell: ({ row }) => {
          const r = row.original;
          const d = optimistic[r.id] ?? decisionOf(r);
          const busy = pending === r.id;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                size="sm"
                variant={d === 'use_stock' ? 'primary' : 'outline'}
                disabled={busy}
                onClick={() =>
                  decide.mutate({
                    id: r.id,
                    // Pressing the choice you already hold clears it, so a decision is
                    // never a one-way door.
                    choice: d === 'use_stock' ? 'pending' : 'use_stock',
                  })
                }
              >
                {d === 'use_stock' ? <Check className="size-3.5" aria-hidden /> : null}
                Use stock
              </Button>
              <Button
                size="sm"
                variant={d === 'buy' ? 'primary' : 'outline'}
                disabled={busy}
                onClick={() =>
                  decide.mutate({ id: r.id, choice: d === 'buy' ? 'pending' : 'buy' })
                }
              >
                {d === 'buy' ? <Check className="size-3.5" aria-hidden /> : null}
                Buy anyway
              </Button>
            </div>
          );
        },
        size: 230,
        enableSorting: false,
        meta: { headerTitle: 'Decide', headerClassName: 'text-end' },
      },
    ],
    [decide, optimistic, pending, runId],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (r) => r.id,
    state: { pagination, sorting, globalFilter: searchQuery },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearchQuery,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    globalFilterFn: (row, _id, value) => {
      const q = String(value ?? '').toLowerCase();
      if (!q) return true;
      const r = row.original;
      return (
        r.sku.toLowerCase().includes(q) ||
        (r.product_name ?? '').toLowerCase().includes(q) ||
        (r.warehouse_code ?? '').toLowerCase().includes(q)
      );
    },
  });

  if (isLoading) {
    return <Skeleton className="h-72 w-full rounded-xl" data-testid="covered-loading" />;
  }

  if (isError) {
    return (
      <Card className="p-8 text-center text-sm text-muted-foreground">
        {error instanceof Error ? error.message : 'Failed to load these rows.'}
      </Card>
    );
  }

  if (!rows.length) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm font-medium">Nothing is waiting on that choice.</p>
        <p className="mt-1 text-2xs text-muted-foreground">
          Every committed line either needs a purchase or has already been decided.
        </p>
      </Card>
    );
  }

  const undecided = rows.filter(
    (r) => (optimistic[r.id] ?? decisionOf(r)) === 'pending',
  ).length;

  return (
    <DataGrid
      table={table}
      recordCount={table.getFilteredRowModel().rows.length}
      listingKey={NO_COLUMN_PERSISTENCE}
      tableLayout={{ width: 'fixed', columnsResizable: true, headerSticky: true }}
      // Keeps the column names on screen while the body scrolls: 193 rows is far enough to
      // forget what a number column was.
      tableClassNames={{ headerSticky: 'sticky top-0 z-10 bg-background shadow-sm' }}
      emptyMessage="No covered line matches this search."
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold">
            Covered by stock
            <span className="ms-2 text-2xs font-normal text-muted-foreground">
              {fmtInt(undecided)} still to decide of {fmtInt(rows.length)}
            </span>
          </h3>
          <div className="relative w-full sm:w-72">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="ps-9 pe-9"
              placeholder="Search SKU, product, or location..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery ? (
              <button
                type="button"
                aria-label="Clear search"
                className="absolute end-2 top-1/2 -translate-y-1/2 rounded-sm p-1 text-muted-foreground hover:text-foreground"
                onClick={() => setSearchQuery('')}
              >
                <X className="size-3.5" />
              </button>
            ) : null}
          </div>
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

export default CoveredByStockView;
