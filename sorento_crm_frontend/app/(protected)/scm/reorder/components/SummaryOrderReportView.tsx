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
import { AlertCircle, ArrowLeft, CheckCircle2, ClipboardList } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { computedAtLabel, dayLabel } from '../lib/coverageTimeline';
import { decisionLockReason, isLegacyRun, planGrainLabel } from '../lib/planGrain';
import { decimalPlacesOf, fmtQty } from '../lib/qtyPrecision';
import {
  useConfirmOrderDecisions,
  useOrderSummary,
  useRecordOrderDecision,
} from '../hooks/useSummaryOrder';
import type {
  OrderSummaryDecisionResult,
  OrderSummaryRow,
} from '../types/summaryOrder.types';
import { DemandDrillPopover } from './DemandDrillPopover';
import { OrderDecisionSheet } from './OrderDecisionSheet';
import { ProductLocationsPopover } from './ProductLocationsPopover';

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
 * Stage 2 keeps that shape and changes nothing about row identity: still ONE row
 * per product (AC-E03). What it adds is the channel reading INSIDE the row - SO
 * demand stacks Project, Retail and Unclassified, and the suggestion stacks firm
 * Project Buy, netted Retail replenishment and the once-rounded total - plus a
 * Locations drill, because a product-wide row cannot answer "where" on its own.
 *
 * The header states the run's stamped **Plan grain**, which is a fact about the
 * run and not a control: plan grain is admin policy (plan section 5.1), so there
 * is no selector here and none in the planning modal. When the run is decided at
 * the other grain, or predates the contract, the decision controls are disabled
 * and say which screen owns the decision instead of failing on save.
 *
 * Phase 1 serves `lib/summaryOrderMockStore`; Phase 2 flips the flag in
 * `services/summaryOrderService.ts` and this component is untouched.
 */

/** One stacked reading inside the SO or Suggested cell. Null is UNAVAILABLE. */
function Reading({
  label,
  value,
  dp,
  emphasis,
  hint,
  children,
}: {
  label: string;
  value: number | null;
  dp: number;
  /** The row's own total, which is the figure a buyer reads first. */
  emphasis?: boolean;
  hint?: string;
  /** The drill, when this reading opens to its contributing lines. */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex w-full items-baseline justify-between gap-2">
      <span className="shrink-0 text-2xs text-muted-foreground" title={hint}>
        {label}
      </span>
      {children ?? (
        <span
          className={cn('tabular-nums', emphasis && 'font-semibold')}
          title={value === null ? 'Unavailable on a legacy plan' : hint}
        >
          {value === null ? (
            <span className="text-2xs text-muted-foreground">Unavailable</span>
          ) : (
            fmtQty(value, dp)
          )}
        </span>
      )}
    </div>
  );
}

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
  /** Returns to the buy co-pilot. This report has no row in that grid to filter back to,
   *  so it needs its own way out - the tile that used to open it is gone. */
  onBack?: () => void;
}

export function SummaryOrderReportView({ runId = null, onBack }: SummaryOrderReportViewProps) {
  // No `as_of`: the report states the date it was frozen for. Asking for a different one
  // would relabel a fixed position, so the only way to read another week is to name its run.
  const query = { run_id: runId };
  const { data, isLoading, isError, error, refetch } = useOrderSummary(query);
  const decide = useRecordOrderDecision(query);
  const confirmDecisionsMutation = useConfirmOrderDecisions(data?.run_id ?? runId ?? null);

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const [deciding, setDeciding] = useState<OrderSummaryRow | null>(null);
  /** The server's refusal, rendered IN the sheet rather than only toasted away. */
  const [decisionError, setDecisionError] = useState<string | null>(null);
  /** The decision just recorded, so its location split is visible immediately. */
  const [justSaved, setJustSaved] = useState<OrderSummaryDecisionResult | null>(null);

  const rows = useMemo<OrderSummaryRow[]>(() => data?.rows ?? [], [data]);
  const reportRunId = data?.run_id ?? runId ?? null;

  /**
   * The run's STAMPED grain (AC-F01). Read off the report, not off the current
   * policy setting: an existing run keeps the grain it was created with, and
   * changing the policy afterwards must not relabel it.
   */
  const runGrain = data
    ? {
        decision_grain: data.decision_grain,
        front_planning_contract_version: data.is_legacy ? null : 1,
      }
    : null;
  const lockReason = decisionLockReason(runGrain, 'product');
  // How many rows Confirm decisions is actually about to materialise into draft POs
  // (AC-C2.8) - `chosen_qty > 0`, not merely decided: a zero decision ("use the pool")
  // is a real answer but confirm skips it (code review, 21 Aug, N6), so counting it
  // here would show a number the toast then contradicts. Zero disables the button
  // rather than hiding it, so the buyer always sees where the action lives.
  const decidedCount = useMemo(
    () => rows.filter((r) => (r.chosen_qty ?? 0) > 0).length,
    [rows],
  );

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
        cell: ({ row }) =>
          fmtQty(row.original.on_hand, decimalPlacesOf(row.original.uom_decimal_places)),
        size: 110,
        meta: { headerTitle: 'On hand', ...numMeta },
      },
      {
        // ONE column, three readings (AC-E03). Channel is analysis INSIDE the row,
        // never row identity, so a product that sells to both sides is still one
        // row and each side is still separately traceable to its own SO lines.
        id: 'so_demand',
        accessorFn: (row) => row.project_demand + row.retail_outstanding,
        header: ({ column }) => <DataGridColumnHeader title="SO demand" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          const dp = decimalPlacesOf(r.uom_decimal_places);
          return (
            <div className="flex w-full flex-col gap-0.5">
              <Reading label="Project" value={r.project_demand} dp={dp} hint="Open Project-class SO quantity">
                <DemandDrillPopover
                  productCode={r.product_code}
                  productName={r.product_name}
                  kind="project"
                  totalQty={r.project_demand}
                  lineCount={r.project_demand_line_count}
                  runId={reportRunId}
                  decimalPlaces={dp}
                />
              </Reading>
              <Reading label="Retail" value={r.retail_outstanding} dp={dp} hint="Open Retail-class SO quantity">
                <span className="flex items-center gap-1">
                  <DemandDrillPopover
                    productCode={r.product_code}
                    productName={r.product_name}
                    kind="retail"
                    totalQty={r.retail_outstanding}
                    lineCount={r.retail_outstanding_line_count}
                    runId={reportRunId}
                    decimalPlaces={dp}
                  />
                </span>
              </Reading>
              {/* An exception, never a third demand class, and since P4 an exception that
                  should not occur: a sales order with no class reads as retail and the SO
                  import refuses a file that would create one. Rendered ONLY where an OLD
                  run still carries a figure, so a report of a clean run does not print a
                  column of zeros for a state the system no longer has. */}
              {r.unclassified_demand_qty ? (
                <Reading
                  label="Unclass."
                  value={r.unclassified_demand_qty}
                  dp={dp}
                  hint="Demand whose sales order carries no demand class"
                >
                  <DemandDrillPopover
                    productCode={r.product_code}
                    productName={r.product_name}
                    kind="unclassified"
                    totalQty={r.unclassified_demand_qty}
                    lineCount={r.unclassified_line_count}
                    runId={reportRunId}
                    decimalPlaces={dp}
                  />
                </Reading>
              ) : null}
              {r.max_days_outstanding !== null ? (
                <span
                  className={cn(
                    'text-end text-2xs tabular-nums',
                    r.max_days_outstanding >= 180 ? 'text-scm-stockout' : 'text-muted-foreground',
                  )}
                >
                  worst {fmtInt(r.max_days_outstanding)} days
                </span>
              ) : null}
            </div>
          );
        },
        size: 210,
        meta: { headerTitle: 'SO demand', ...numMeta },
      },
      {
        // Where the product-wide row's figures actually sit. Under Product policy
        // this is a read and drill view of the same frozen facts (AC-F02 / AC-F08).
        id: 'locations',
        header: ({ column }) => <DataGridColumnHeader title="Locations" column={column} />,
        cell: ({ row }) => (
          <ProductLocationsPopover
            productCode={row.original.product_code}
            productName={row.original.product_name}
            runId={reportRunId}
            decimalPlaces={decimalPlacesOf(row.original.uom_decimal_places)}
          />
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Locations' },
      },
      {
        // Separate from in transit on purpose (AC-C2.2): this half can still be
        // re-dated or cancelled, so it is the half a decider can act on.
        accessorKey: 'qty_on_order',
        header: ({ column }) => <DataGridColumnHeader title="Ordered" column={column} />,
        cell: ({ row }) =>
          fmtQty(row.original.qty_on_order, decimalPlacesOf(row.original.uom_decimal_places)),
        size: 120,
        meta: { headerTitle: 'Ordered', ...numMeta },
      },
      {
        accessorKey: 'qty_in_transit',
        header: ({ column }) => <DataGridColumnHeader title="Incoming" column={column} />,
        cell: ({ row }) =>
          fmtQty(row.original.qty_in_transit, decimalPlacesOf(row.original.uom_decimal_places)),
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
            {fmtQty(row.original.shortfall, decimalPlacesOf(row.original.uom_decimal_places))}
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
        // The two channels that make up the suggestion, and the ONE total the
        // supplier's MOQ and multiple were applied to (AC-E06 / AC-F11). Project
        // Buy is firm - the Retail reorder level cannot suppress it (AC-E05) - and
        // sits beside the SO column's Project reading as the second of the row's
        // two Project measures.
        cell: ({ row }) => {
          const r = row.original;
          const dp = decimalPlacesOf(r.uom_decimal_places);
          return (
            <div className="flex w-full flex-col gap-0.5">
              <Reading
                label="Project Buy"
                value={r.project_buy_qty}
                dp={dp}
                hint="Confirmed unplaced Buy. Firm: Retail netting never reduces it"
              />
              <Reading
                label="Retail"
                value={r.retail_replenishment_qty}
                dp={dp}
                hint="Netted Retail replenishment across locations"
              >
                {r.retail_replenishment_qty === null ? undefined : (
                  // The Retail suggestion opens to the evidence it was netted from:
                  // per-location stock, velocity, incoming, reorder level and the
                  // allocation (AC-E07). The SO column's Retail reading opens to the
                  // ORDER lines instead - two different questions, two drills.
                  <ProductLocationsPopover
                    productCode={r.product_code}
                    productName={r.product_name}
                    runId={reportRunId}
                    decimalPlaces={dp}
                  >
                    <button
                      type="button"
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Retail replenishment evidence for ${r.product_code}`}
                      className="rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {fmtQty(r.retail_replenishment_qty, dp)}
                    </button>
                  </ProductLocationsPopover>
                )}
              </Reading>
              <Reading
                label="Total"
                value={r.suggested_qty}
                dp={dp}
                emphasis
                hint="Rounded once at the supplier MOQ and order multiple, for the whole product"
              />
            </div>
          );
        },
        size: 190,
        meta: { headerTitle: 'Suggested (policy)', ...numMeta },
      },
      {
        accessorKey: 'chosen_qty',
        header: ({ column }) => <DataGridColumnHeader title="Order qty" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          const dp = decimalPlacesOf(r.uom_decimal_places);
          // The run is decided at the other grain, or predates the contract. The
          // control is disabled and names the screen that owns the decision, rather
          // than accepting a quantity the server will refuse (AC-F09 / AC-F10).
          if (lockReason) {
            return (
              <span
                className="tabular-nums text-muted-foreground"
                data-testid={`chosen-qty-locked-${r.product_code}`}
                title={lockReason}
              >
                {r.chosen_qty === null ? EM_DASH : fmtQty(r.chosen_qty, dp)}
              </span>
            );
          }
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
              {fmtQty(r.chosen_qty, dp)}
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
          if (lockReason) {
            return r.chosen_supplier_name ? (
              <span className="truncate text-muted-foreground" title={lockReason}>
                {r.chosen_supplier_name}
              </span>
            ) : (
              <span className="text-muted-foreground" title={lockReason}>
                {EM_DASH}
              </span>
            );
          }
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
    [reportRunId, lockReason],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.product_code,
    state: { pagination, sorting, globalFilter: searchQuery },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
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
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => void refetch()}>
            Try again
          </Button>
          {onBack ? (
            <Button variant="ghost" onClick={onBack}>
              <ArrowLeft className="size-3.5" />
              Back to plan
            </Button>
          ) : null}
        </div>
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
          {/* "the outstanding order book" named an action that is now called Upload sales
              orders / Upload purchase orders everywhere it can be started from. One action,
              one name. */}
          No product is short in this plan. Upload the order book, or generate a plan, to
          build a new report.
        </p>
        {onBack ? (
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="size-3.5" />
            Back to plan
          </Button>
        ) : null}
      </Card>
    );
  }

  const recordCount = table.getFilteredRowModel().rows.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          {onBack ? (
            <Button variant="ghost" size="sm" className="-ms-2 mb-1 h-7 gap-1 px-2 text-muted-foreground" onClick={onBack}>
              <ArrowLeft className="size-3.5" />
              Back to plan
            </Button>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold">Summary order report</h3>
            {/* A FACT about the run, not a control: plan grain is admin policy and
                this run stamped it at creation (AC-F01). */}
            {data ? (
              <Badge
                variant={isLegacyRun(runGrain) ? 'secondary' : 'info'}
                appearance="light"
                size="sm"
                data-testid="plan-grain-chip"
              >
                {planGrainLabel(runGrain)}
              </Badge>
            ) : null}
          </div>
          <p className="text-2xs text-muted-foreground">
            {!data
              ? 'Loading'
              : data.as_of
                ? `As of ${dayLabel(data.as_of)} · computed ${computedAtLabel(data.generated_at)}`
                : 'No plan has been frozen yet, so there is nothing to state a date for'}
          </p>
          {lockReason ? (
            <p className="text-2xs text-muted-foreground" data-testid="grain-lock-note">
              {lockReason}
            </p>
          ) : null}
        </div>
        {/* Product-grain only (AC-F09): decide-on-the-row here, Confirm decisions
            materialises every chosen quantity into a consolidated draft PO the same
            way the location-grain "buy" tab already does (captain, 21 Aug). Disabled
            rather than hidden with nothing decided, so the action's home is always
            visible. */}
        {!lockReason && data ? (
          <Button
            size="sm"
            className="shrink-0"
            data-testid="confirm-order-decisions"
            disabled={decidedCount === 0 || confirmDecisionsMutation.isPending}
            onClick={() => confirmDecisionsMutation.mutate()}
          >
            <CheckCircle2 className="size-4" />
            Confirm decisions{decidedCount > 0 ? ` (${decidedCount})` : ''}
          </Button>
        ) : null}
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
            <ListSearchInput
              value={searchInput}
              onChange={setSearchInput}
              placeholder="Search product or supplier..."
              aria-label="Search product or supplier"
              className="w-full sm:w-64"
            />
          </CardHeader>
          <CardTable>
            {/* The report is wide by nature - eleven figures per product - so it
                scrolls inside its own container rather than the page. */}
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <OrderDecisionSheet
        row={deciding}
        open={!!deciding}
        onOpenChange={(o) => {
          if (o) return;
          setDeciding(null);
          setDecisionError(null);
          setJustSaved(null);
        }}
        isSaving={decide.isPending}
        lockReason={lockReason}
        saveError={decisionError}
        saved={justSaved}
        onSave={(input) => {
          if (!deciding) return;
          const productCode = deciding.product_code;
          setDecisionError(null);
          setJustSaved(null);
          decide.mutate(
            {
              productCode,
              input: {
                run_id: reportRunId ?? '',
                chosen_qty: input.chosen_qty,
                supplier_code: input.supplier_code,
              },
              // The row's FROZEN precision, so the confirmation states the same
              // quantity that was accepted (AC-F12).
              decimalPlaces: deciding.uom_decimal_places,
            },
            {
              // The sheet STAYS OPEN on both outcomes: a refusal has to be readable
              // where the quantity was typed, and a success has a location split
              // worth seeing before the sheet goes away (AC-F08 / AC-F12).
              onSuccess: (result) => setJustSaved(result),
              onError: (e: Error) => setDecisionError(e.message),
            },
          );
        }}
      />
    </div>
  );
}

export default SummaryOrderReportView;
