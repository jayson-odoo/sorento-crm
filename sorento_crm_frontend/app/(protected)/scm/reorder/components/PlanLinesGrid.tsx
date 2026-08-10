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
import { Info, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtInt, fmtMoney, fmtSigned } from '../../lib/format';
import {
  PLAN_LINE_STATUS_LABEL,
  PLAN_LINE_STATUS_ORDER,
  type PlanLine,
  type PlanLineStatus,
} from '../lib/planLine';
import { decidedCost, decidedQty, type PlanDecisionMap } from '../lib/planDecisions';
import { describeCover, NO_COVER, type CoverProposal } from '../lib/coverPlan';
import { PRICE_ADVICE_SORT, type CheaperAlternative, type PriceAdvice } from '../lib/priceAdvice';
import type { TrajectoryEntry } from '../lib/trajectory';
import { PlanTrendPopover } from './PlanTrendPopover';
import { PlanLineDecisionCell } from './PlanLineDecisionCell';
import { PlanPriceCell } from './PlanPriceCell';
import { PlanChecklistPopover } from './PlanChecklistPopover';
import { PlanDemandPopover } from './PlanDemandPopover';
import {
  DaysCoverDrill,
  ExplainNumber,
  NetDrill,
  OrderQtyDrill,
} from './PlanExplainDrills';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * ONE grid for every line of a plan.
 *
 * > "ALL should be in 1 table, 1 list, 1 data grid table, you don't tell me what's over or
 * >  within budget, because I haven't decided which one i want to buy"
 *
 * Replaces six separate surfaces. The classification the buyer used to navigate by is now the
 * `Status` column, and there is deliberately NO budget here: within and over are the result of
 * step 4, not a property of a line.
 *
 * The offsets the engine netted (on hand, incoming, on order) are COLUMNS, because burying
 * them in a popover is what made the netting feel like a decision taken on the buyer's behalf.
 * Read left to right the row is an argument: this much is needed, this much we already have,
 * so this much to buy.
 */

const STATUS_VARIANT: Record<PlanLineStatus, 'primary' | 'warning' | 'secondary' | 'info'> = {
  buy: 'primary',
  no_price: 'warning',
  needs_level: 'warning',
  covered_by_stock: 'info',
  allocation: 'secondary',
  exception: 'warning',
};

/**
 * Swallows a click so it never reaches the row.
 *
 * The row opens the full derivation, and `onRowClick` is handed the row rather than the
 * event, so it cannot tell an interactive cell from the row itself. Without this, adjusting a
 * quantity or opening a drill would also open the dialog on top of what you were doing.
 */
function StopClick({ children }: { children: React.ReactNode }) {
  return (
    <span onClick={(e) => e.stopPropagation()} className="contents">
      {children}
    </span>
  );
}

/** A dash means "not on file", which is a different fact from zero and must not read as it. */
function numCell(value: number | null | undefined) {
  return value === null || value === undefined ? (
    <span className="text-muted-foreground">{EM_DASH}</span>
  ) : (
    fmtInt(value)
  );
}

export function PlanLinesGrid({
  lines,
  decisions,
  onDecide,
  onClear,
  coverFor,
  priceFor,
  cheaperFor,
  trendFor,
  staleAfterDays = 180,
  statusFilter: statusFilterProp = null,
  onStatusFilterChange,
  runId,
  isLoading,
}: {
  lines: PlanLine[];
  decisions: PlanDecisionMap;
  onDecide: (
    line: PlanLine,
    next: { kind: 'buy' | 'use_stock' | 'skip'; qty?: number; reason?: string },
  ) => void;
  /** Return a line to undecided. Separate from `onDecide` because undecided is the absence
   *  of a decision, not a fourth kind of one. */
  onClear: (line: PlanLine) => void;
  /** What the plan suggests for a line: buy, cover from elsewhere, or a split of the two. */
  coverFor?: (line: PlanLine) => CoverProposal;
  /** What we last paid this line's supplier, and how old that is. Undefined = no opinion. */
  priceFor?: (line: PlanLine) => PriceAdvice | undefined;
  /** S13e: a materially cheaper supplier on the line's own shortlist, when one exists. */
  cheaperFor?: (line: PlanLine) => CheaperAlternative | null;
  /** Is this product's demand sustaining or dying off, on this line's side. */
  trendFor?: (line: PlanLine) => TrajectoryEntry | undefined;
  /** The age past which the business stops trusting a price. Shown, not implied. */
  staleAfterDays?: number;
  /** Status the list is narrowed to, or null for the whole plan. Controlled so the summary
   *  tiles can narrow it: they used to reveal a band, and there are no bands now. */
  statusFilter?: PlanLineStatus | null;
  onStatusFilterChange?: (next: PlanLineStatus | null) => void;
  /** The run on screen, threaded to each row's demand drill so it can fetch its order lines. */
  runId?: string | null;
  isLoading?: boolean;
}) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  // Rank ascending is the engine's own priority order, so it is the order the buyer works in.
  const [sorting, setSorting] = useState<SortingState>([{ id: 'rank', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const statusFilter: string = statusFilterProp ?? 'all';
  const setStatusFilter = (next: string) =>
    onStatusFilterChange?.(next === 'all' ? null : (next as PlanLineStatus));
  // Undecided first by default is a deliberate bias toward the work that is left. It is a
  // filter, not a sort, so it never reorders the priority the engine computed.
  const [decidedFilter, setDecidedFilter] = useState<string>('all');
  // Row click opens the full derivation, as it did before the grid was rebuilt. The pager
  // steps through the rows in the order they are currently sorted and filtered, so "next"
  // means the next line the buyer is actually looking at.
  const [detailRec, setDetailRec] = useState<ReorderRecommendation | null>(null);

  const filtered = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    return lines.filter((l) => {
      if (statusFilter !== 'all' && l.status !== statusFilter) return false;
      if (decidedFilter === 'undecided' && decisions[l.id]) return false;
      if (decidedFilter === 'decided' && !decisions[l.id]) return false;
      if (!needle) return true;
      return (
        l.sku.toLowerCase().includes(needle) ||
        l.product_name.toLowerCase().includes(needle) ||
        l.warehouse.toLowerCase().includes(needle) ||
        l.supplier.name.toLowerCase().includes(needle)
      );
    });
  }, [lines, searchQuery, statusFilter, decidedFilter, decisions]);

  const columns = useMemo<ColumnDef<PlanLine>[]>(
    () => [
      {
        id: 'rank',
        accessorFn: (row) => row.rankOrder ?? Number.MAX_SAFE_INTEGER,
        header: ({ column }) => <DataGridColumnHeader title="#" visibility column={column} />,
        // An unranked line shows a dash rather than a number the engine never assigned.
        cell: ({ row }) =>
          row.original.rankOrder === null ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            <span className="tabular-nums">{row.original.rankOrder}</span>
          ),
        size: 64,
        enableSorting: true,
        meta: { headerTitle: 'Priority', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        id: 'sku',
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="Product" visibility column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 space-y-px">
            <div className="flex items-center gap-1.5">
              <span className="truncate text-sm font-medium" title={row.original.sku}>
                {row.original.sku}
              </span>
              {/* Which orders this quantity is for, and the lookups the buyer used to do by
                  hand. Both were on the old row and are the reason a number is trustworthy. */}
              <StopClick>
                <PlanDemandPopover runId={runId ?? null} recId={row.original.id} />
                <PlanChecklistPopover rec={row.original.rec} />
              </StopClick>
            </div>
            <div className="truncate text-xs text-muted-foreground" title={row.original.product_name}>
              {row.original.product_name}
            </div>
          </div>
        ),
        size: 240,
        enableSorting: true,
        enableHiding: false,
        meta: {
          headerTitle: 'Product',
          skeleton: (
            <div className="space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          ),
        },
      },
      {
        id: 'warehouse',
        accessorKey: 'warehouse',
        header: ({ column }) => <DataGridColumnHeader title="Location" visibility column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.warehouse}>
            {row.original.warehouse}
          </span>
        ),
        size: 130,
        enableSorting: true,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'side',
        accessorFn: (row) => row.rec.segment ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Side" visibility column={column} />,
        // Project vs Retail, off the warehouse's segment. Never merged into one figure
        // anywhere on this screen (S13b): project demand is erratic and retail stable, so a
        // number spanning both describes neither. "Retail" not "Dealer" - the user's word.
        cell: ({ row }) => {
          const seg = row.original.rec.segment;
          if (!seg) return <span className="text-muted-foreground">{EM_DASH}</span>;
          return (
            <Badge variant={seg === 'project' ? 'info' : 'success'} appearance="light" size="sm">
              {seg === 'project' ? 'Project' : 'Retail'}
            </Badge>
          );
        },
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'Side', skeleton: <Skeleton className="h-5 w-14" /> },
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" visibility column={column} />,
        cell: ({ row }) => (
          <Badge variant={STATUS_VARIANT[row.original.status]} appearance="light" size="sm">
            {PLAN_LINE_STATUS_LABEL[row.original.status]}
          </Badge>
        ),
        size: 140,
        enableSorting: true,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-5 w-20" /> },
      },
      {
        id: 'needed',
        accessorFn: (row) => row.rec.outstanding_sales ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Needed" visibility column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">{numCell(row.original.rec.outstanding_sales)}</span>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'Needed', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      // The three offsets, on the row rather than behind a popover. This is the arithmetic
      // that produced the suggested quantity, and the buyer has to be able to see it without
      // opening anything.
      {
        id: 'on_hand',
        accessorFn: (row) => row.rec.on_hand ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="On hand" visibility column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{numCell(row.original.rec.on_hand)}</span>,
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'On hand', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'incoming_spo',
        accessorFn: (row) => row.rec.incoming_spo ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Incoming" visibility column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">{numCell(row.original.rec.incoming_spo)}</span>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'Incoming', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'outstanding_po',
        accessorFn: (row) => row.rec.outstanding_po ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="On order" visibility column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">{numCell(row.original.rec.outstanding_po)}</span>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'On order', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'suggested',
        accessorFn: (row) => row.order_qty,
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested" visibility column={column} />
        ),
        cell: ({ row }) =>
          row.original.purchasable ? (
            <span className="inline-flex items-center gap-1">
              <span className="tabular-nums">{fmtInt(row.original.order_qty)}</span>
              <StopClick>
              <Popover>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    title="How we got this qty"
                    aria-label={`Explain order qty for ${row.original.sku}`}
                    className="rounded-sm text-muted-foreground/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Info className="size-3.5" aria-hidden />
                  </button>
                </PopoverTrigger>
                <PopoverPortal>
                  <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
                    <OrderQtyDrill row={row.original} />
                  </PopoverContent>
                </PopoverPortal>
              </Popover>
              </StopClick>
            </span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ),
        size: 120,
        enableSorting: true,
        meta: { headerTitle: 'Suggested', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'net',
        accessorFn: (row) => row.net ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Net" visibility column={column} />,
        cell: ({ row }) => (
          <StopClick>
            <ExplainNumber value={fmtSigned(row.original.net)} title="Explain net">
              <NetDrill row={row.original} />
            </ExplainNumber>
          </StopClick>
        ),
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Net', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'days_cover',
        accessorFn: (row) => row.days_cover ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="Runway" visibility column={column} />,
        cell: ({ row }) => (
          <StopClick>
            <ExplainNumber
              value={row.original.days_cover === null ? EM_DASH : fmtInt(row.original.days_cover)}
              title="Explain runway"
            >
              <DaysCoverDrill row={row.original} />
            </ExplainNumber>
          </StopClick>
        ),
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Runway', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'cost',
        accessorFn: (row) => decidedCost(row, decisions[row.id]) ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="Cost" visibility column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (!line.purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;
          const qty = decidedQty(line, decisions[line.id]) || line.order_qty;
          const cost = decidedCost({ ...line }, { kind: 'buy', qty });
          // A price we do not hold is never rendered as a number: it is the reason the line
          // cannot be weighed against a budget. A dash rather than the words, because the
          // Status column on the same row already says "No price" and printing it twice is
          // noise; the title carries the detail for anyone who hides that column.
          return cost === null ? (
            <span className="text-muted-foreground" title="No price on file, so this line cannot be costed">
              {EM_DASH}
            </span>
          ) : (
            <span className="tabular-nums">{fmtMoney(cost)}</span>
          );
        },
        size: 120,
        enableSorting: true,
        meta: { headerTitle: 'Cost', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'price',
        // Sorted by how urgent the price question is, not alphabetically: a line costing at
        // zero has to be reachable in one click from the top of the column.
        accessorFn: (row) => {
          const p = priceFor?.(row);
          return p ? PRICE_ADVICE_SORT[p.advice] : 99;
        },
        header: ({ column }) => (
          <DataGridColumnHeader title="Price to use" visibility column={column} />
        ),
        cell: ({ row }) => (
          <StopClick>
            <PlanPriceCell
              price={priceFor?.(row.original)}
              cheaper={cheaperFor?.(row.original) ?? null}
              staleAfterDays={staleAfterDays}
              purchasable={row.original.purchasable}
            />
          </StopClick>
        ),
        size: 190,
        enableSorting: true,
        meta: { headerTitle: 'Price to use', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'suggestion',
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested action" visibility column={column} />
        ),
        cell: ({ row }) => {
          const line = row.original;
          if (!line.purchasable) {
            return <span className="text-muted-foreground">{EM_DASH}</span>;
          }
          const cover = coverFor?.(line) ?? NO_COVER;
          // Structured parts, one per line, never a comma-joined sentence (user markup,
          // 2026-08-10: "I need it to be more structured and organized"). The full prose
          // stays on the title and in the decision cell's tooltip for anyone who wants it.
          const buyQty = cover.coverQty > 0 ? cover.buyQty : Math.ceil(line.order_qty);
          const crossing = cover.sources.some((x) => x.cross_segment);
          // A cover offer on a project line is purchasing superseding CS: the inquiry said
          // buy it all, and the engine found stock CS did not use. Said out loud, because a
          // quiet disagreement with CS reads as the engine miscounting.
          const supersede =
            line.rec.segment === 'project' && cover.coverQty > 0
              ? `CS asked to buy ${fmtInt(Math.ceil(line.order_qty))}`
              : null;
          return (
            <div className="min-w-0 text-xs" title={describeCover(cover, (n) => fmtInt(n))}>
              {cover.coverQty > 0 ? (
                <div className="truncate">
                  {`Use stock ${cover.sources
                    .map((s) => `${fmtInt(s.qty)} from ${s.warehouse_code}`)
                    .join(', ')}`}
                </div>
              ) : null}
              {buyQty > 0 ? (
                <div className="truncate font-medium">{`Buy ${fmtInt(buyQty)}`}</div>
              ) : null}
              {crossing ? (
                <span className="text-2xs text-scm-overstock">crosses segment</span>
              ) : null}
              {supersede ? (
                <span className="block truncate text-2xs text-muted-foreground">
                  {supersede}
                </span>
              ) : null}
              {/* Trend: the sustain-or-die-off judgment (S13d), clickable for the line
                  graph and the orders behind it. */}
              <StopClick>
                <PlanTrendPopover trend={trendFor?.(line)} />
              </StopClick>
            </div>
          );
        },
        size: 210,
        enableSorting: false,
        meta: { headerTitle: 'Suggested action', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'decision',
        header: ({ column }) => <DataGridColumnHeader title="Decision" visibility column={column} />,
        cell: ({ row }) => (
          <StopClick>
          <PlanLineDecisionCell
            line={row.original}
            decision={decisions[row.original.id]}
            cover={coverFor?.(row.original) ?? NO_COVER}
            onDecide={(next) => onDecide(row.original, next)}
            onClear={() => onClear(row.original)}
          />
          </StopClick>
        ),
        size: 260,
        enableSorting: false,
        enableHiding: false,
        meta: { headerTitle: 'Decision', skeleton: <Skeleton className="h-8 w-40" /> },
      },
    ],
    [decisions, onDecide, onClear, runId, coverFor, priceFor, cheaperFor, trendFor, staleAfterDays],
  );

  const [columnOrder, setColumnOrder] = useState<string[]>(() =>
    columns.map((c) => c.id as string),
  );

  const table = useReactTable({
    columns,
    data: filtered,
    pageCount: Math.ceil(filtered.length / pagination.pageSize),
    getRowId: (row: PlanLine) => row.id,
    state: { pagination, sorting, columnOrder },
    columnResizeMode: 'onChange',
    onColumnOrderChange: setColumnOrder,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const pageRecs = useMemo<ReorderRecommendation[]>(
    () => table.getRowModel().rows.map((r) => r.original.rec),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [table, filtered, pagination, sorting],
  );

  const statusOptions = useMemo(
    () => [
      { value: 'all', label: 'All statuses' },
      ...PLAN_LINE_STATUS_ORDER.map((s) => ({ value: s, label: PLAN_LINE_STATUS_LABEL[s] })),
    ],
    [],
  );

  const Toolbar = () => (
    <CardHeader className="block">
      <DataGridListToolbar
        table={table}
        searchSlot={
          <div className="relative">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search product, location, or supplier"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full ps-9 sm:w-64 md:w-80"
            />
            {searchQuery.length > 0 && (
              <Button
                mode="icon"
                variant="dim"
                className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                <X />
              </Button>
            )}
          </div>
        }
        filters={{
          kind: 'custom',
          active: statusFilter !== 'all' || decidedFilter !== 'all',
          activeCount: (statusFilter !== 'all' ? 1 : 0) + (decidedFilter !== 'all' ? 1 : 0),
          content: (
            <div className="space-y-3">
              <p className="text-sm font-medium">Filters</p>
              <SearchableSelect
                value={statusFilter}
                onChange={setStatusFilter}
                options={statusOptions}
                placeholder="Status"
              />
              <SearchableSelect
                value={decidedFilter}
                onChange={setDecidedFilter}
                options={[
                  { value: 'all', label: 'Decided and undecided' },
                  { value: 'undecided', label: 'Still to decide' },
                  { value: 'decided', label: 'Already decided' },
                ]}
                placeholder="Decision"
              />
            </div>
          ),
        }}
      />
    </CardHeader>
  );

  return (
    <DataGrid
      table={table}
      recordCount={filtered.length}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsPinnable: true,
        columnsMovable: true,
        columnsVisibility: true,
      }}
      tableClassNames={{ edgeCell: 'px-5' }}
      onRowClick={(row) => setDetailRec(row.rec)}
    >
      <Card>
        <Toolbar />
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <ReorderExplanationDialog
        rec={detailRec}
        open={!!detailRec}
        onOpenChange={(o) => !o && setDetailRec(null)}
        recs={pageRecs}
        totalCount={filtered.length}
        pageItemOffset={pagination.pageIndex * pagination.pageSize}
        onNavigate={setDetailRec}
      />
    </DataGrid>
  );
}
