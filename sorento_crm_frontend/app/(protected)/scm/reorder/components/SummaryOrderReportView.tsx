'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { AlertCircle, ClipboardList, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import { computedAtLabel, dayLabel } from '../lib/coverageTimeline';
import { useOrderSummary, useRecordOrderDecision } from '../hooks/useSummaryOrder';
import type { OrderSummaryRow } from '../types/summaryOrder.types';
import { DemandDrillPopover } from './DemandDrillPopover';
import { OrderDecisionSheet } from './OrderDecisionSheet';

/**
 * The Summary Order Report (UAC Group C2 + C3).
 *
 * Today this is a printed sheet whose TOTAL ORDER QTY column is blank and filled
 * in by hand in pen. The screen keeps the sheet's shape - one row per product,
 * network wide (AC-C2.1) - and changes exactly two things about it: the
 * aggregates can be opened, and the quantity can be written down where it will
 * be read again.
 *
 * What the row carries is deliberately short. Every aggregate opens behind an
 * information icon rather than rendering inline (AC-C2.2a), because the list has
 * to hold only what is needed to decide; preventing information fatigue is a
 * requirement, not a preference. Ordered and Incoming are separate columns
 * (AC-C2.2): only Incoming is in the net position, and Ordered is there so a
 * shortfall does not read as "nobody has done anything about this". The engine's
 * suggested quantity sits immediately beside the chosen one (AC-C2.8), so a
 * larger number is visibly a decision rather than a silent override.
 *
 * Phase 1 serves `lib/summaryOrderMockStore`; Phase 2 flips the flag in
 * `services/summaryOrderService.ts` and this component is untouched.
 */

/**
 * This grid shares `/scm/reorder` with the buy co-pilot and the allocation list,
 * and pathname-derived column persistence would have the three clobber each
 * other's saved columns. An empty key opts out, as the coverage grids do.
 */
const NO_COLUMN_PERSISTENCE = '';

const numMeta = { headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' };

export interface SummaryOrderReportViewProps {
  /** Opaque run key. Null reads the newest completed plan. Never rendered. */
  runId?: string | null;
}

export function SummaryOrderReportView({ runId = null }: SummaryOrderReportViewProps) {
  // No `as_of`: the report states the date it was frozen for. Asking for a different one
  // would relabel a fixed position, so the only way to read another week is to name its run.
  const query = { run_id: runId };
  const { data, isLoading, isError, error, refetch } = useOrderSummary(query);
  const decide = useRecordOrderDecision(query);

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [deciding, setDeciding] = useState<OrderSummaryRow | null>(null);

  const rows = useMemo<OrderSummaryRow[]>(() => data?.rows ?? [], [data]);
  const reportRunId = data?.run_id ?? runId ?? null;

  const columns = useMemo<ColumnDef<OrderSummaryRow>[]>(
    () => [
      {
        accessorKey: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium" title={row.original.product_code}>
              {row.original.product_code}
            </span>
            <span
              className="truncate text-xs text-muted-foreground"
              title={row.original.product_name ?? undefined}
            >
              {row.original.product_name ?? EM_DASH}
            </span>
          </div>
        ),
        size: 240,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-8 w-40" /> },
      },
      {
        accessorKey: 'on_hand',
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        cell: ({ row }) => fmtInt(row.original.on_hand),
        size: 110,
        meta: { headerTitle: 'On hand', ...numMeta },
      },
      {
        accessorKey: 'project_demand',
        header: ({ column }) => <DataGridColumnHeader title="Project demand" column={column} />,
        cell: ({ row }) => (
          <DemandDrillPopover
            productCode={row.original.product_code}
            productName={row.original.product_name}
            kind="project"
            totalQty={row.original.project_demand}
            lineCount={row.original.project_demand_line_count}
            runId={reportRunId}
          />
        ),
        size: 160,
        meta: { headerTitle: 'Project demand', ...numMeta },
      },
      {
        accessorKey: 'dealer_outstanding',
        header: ({ column }) => <DataGridColumnHeader title="Dealer outstanding" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col items-end gap-0.5">
            <DemandDrillPopover
              productCode={row.original.product_code}
              productName={row.original.product_name}
              kind="dealer"
              totalQty={row.original.dealer_outstanding}
              lineCount={row.original.dealer_outstanding_line_count}
              runId={reportRunId}
            />
            {row.original.max_days_outstanding !== null ? (
              <span
                className={cn(
                  'text-2xs tabular-nums',
                  row.original.max_days_outstanding >= 180
                    ? 'text-scm-stockout'
                    : 'text-muted-foreground',
                )}
              >
                worst {fmtInt(row.original.max_days_outstanding)} days
              </span>
            ) : null}
          </div>
        ),
        size: 180,
        meta: { headerTitle: 'Dealer outstanding', ...numMeta },
      },
      {
        // Separate from in transit on purpose (AC-C2.2): this half can still be
        // re-dated or cancelled, so it is the half a decider can act on.
        accessorKey: 'qty_on_order',
        header: ({ column }) => <DataGridColumnHeader title="Ordered" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_on_order),
        size: 120,
        meta: { headerTitle: 'Ordered', ...numMeta },
      },
      {
        accessorKey: 'qty_in_transit',
        header: ({ column }) => <DataGridColumnHeader title="Incoming" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_in_transit),
        size: 120,
        meta: { headerTitle: 'Incoming', ...numMeta },
      },
      // These two columns answer DIFFERENT questions and sit side by side, so each names
      // the demand it is about. On the real book 317 of 317 planned rows read "0" here and
      // a non-zero suggestion beside it - not a contradiction, but it reads as one under
      // the bare labels "Shortfall" and "Suggested": there is almost no committed order
      // book, while the policy still says restock against forecast history.
      {
        accessorKey: 'shortfall',
        header: ({ column }) => (
          // `title` on this component is the LABEL, not an HTML tooltip, so the
          // clarification lives on the cell instead.
          <DataGridColumnHeader title="Short vs orders" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className={cn(row.original.shortfall > 0 && 'font-medium text-scm-stockout')}
            title="The dated gap against committed orders"
          >
            {fmtInt(row.original.shortfall)}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Short vs orders', ...numMeta },
      },
      {
        accessorKey: 'suggested_qty',
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested (policy)" column={column} />
        ),
        cell: ({ row }) => (
          <span title="What the reorder policy proposes against forecast demand, not against the orders on the book">
            {fmtInt(row.original.suggested_qty)}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Suggested (policy)', ...numMeta },
      },
      {
        accessorKey: 'chosen_qty',
        header: ({ column }) => <DataGridColumnHeader title="Order qty" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          if (r.chosen_qty === null) {
            return (
              <Button
                variant="outline"
                size="sm"
                data-testid={`set-qty-${r.product_code}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setDeciding(r);
                }}
              >
                Set
              </Button>
            );
          }
          return (
            <button
              type="button"
              data-testid={`chosen-qty-${r.product_code}`}
              onClick={(e) => {
                e.stopPropagation();
                setDeciding(r);
              }}
              className="w-full rounded-sm text-end font-semibold tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title={
                r.decided_by
                  ? `Set by ${r.decided_by}${r.decided_at ? ` on ${dayLabel(r.decided_at.slice(0, 10))}` : ''}`
                  : undefined
              }
            >
              {fmtInt(r.chosen_qty)}
            </button>
          );
        },
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Order qty', ...numMeta },
      },
      {
        accessorKey: 'chosen_supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          return (
            <button
              type="button"
              data-testid={`supplier-cell-${r.product_code}`}
              onClick={(e) => {
                e.stopPropagation();
                setDeciding(r);
              }}
              className="flex w-full min-w-0 items-center rounded-sm text-start focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {r.chosen_supplier_name ? (
                <span className="truncate" title={r.chosen_supplier_name}>
                  {r.chosen_supplier_name}
                </span>
              ) : (
                <Badge variant="secondary" appearance="light" size="md">
                  Choose
                </Badge>
              )}
            </button>
          );
        },
        size: 200,
        meta: { headerTitle: 'Supplier' },
      },
    ],
    [reportRunId],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.product_code,
    state: { pagination, sorting, globalFilter: searchQuery },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearchQuery,
    globalFilterFn: (row, _columnId, filterValue) => {
      const q = String(filterValue).toLowerCase().trim();
      if (!q) return true;
      const r = row.original;
      return (
        r.product_code.toLowerCase().includes(q) ||
        (r.product_name ?? '').toLowerCase().includes(q) ||
        (r.chosen_supplier_name ?? '').toLowerCase().includes(q)
      );
    },
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // ---- error ---------------------------------------------------------------
  if (isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="size-5" aria-hidden />
        </span>
        <p className="max-w-sm text-sm text-muted-foreground">
          {error instanceof Error ? error.message : 'Failed to load the order summary.'}
        </p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </Card>
    );
  }

  // ---- empty ---------------------------------------------------------------
  if (!isLoading && rows.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-3 p-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <ClipboardList className="size-6" aria-hidden />
        </span>
        <div className="text-base font-semibold">Nothing to order</div>
        <p className="max-w-md text-sm text-muted-foreground">
          No product is short in this plan. Upload the outstanding order book, or generate a plan,
          to build a new report.
        </p>
      </Card>
    );
  }

  const recordCount = table.getFilteredRowModel().rows.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h3 className="text-base font-semibold">Summary order report</h3>
          <p className="text-2xs text-muted-foreground">
            {!data
              ? 'Loading'
              : data.as_of
                ? `As of ${dayLabel(data.as_of)} · computed ${computedAtLabel(data.generated_at)}`
                : 'No plan has been frozen yet, so there is nothing to state a date for'}
          </p>
        </div>
      </div>

      <DataGrid
        table={table}
        recordCount={recordCount}
        isLoading={isLoading}
        listingKey={NO_COLUMN_PERSISTENCE}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No product matches this search."
        onRowClick={(row) => {
          (document.activeElement as HTMLElement | null)?.blur();
          setDeciding(row);
        }}
      >
        <Card>
          <CardHeader className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative">
              <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search product or supplier..."
                aria-label="Search product or supplier"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full ps-9 sm:w-64"
              />
              {searchQuery ? (
                <Button
                  mode="icon"
                  variant="dim"
                  className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                >
                  <X />
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardTable>
            {/* The report is wide by nature - eleven figures per product - so it
                scrolls inside its own container rather than the page. */}
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <OrderDecisionSheet
        row={deciding}
        open={!!deciding}
        onOpenChange={(o) => !o && setDeciding(null)}
        isSaving={decide.isPending}
        onSave={(input) => {
          if (!deciding) return;
          const productCode = deciding.product_code;
          setDeciding(null);
          decide.mutate({
            productCode,
            input: {
              run_id: reportRunId ?? '',
              chosen_qty: input.chosen_qty,
              supplier_code: input.supplier_code,
            },
          });
        }}
      />
    </div>
  );
}

export default SummaryOrderReportView;
