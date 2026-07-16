'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  RowSelectionState,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Popover as PopoverPrimitive } from 'radix-ui';
import {
  Check,
  CheckCircle2,
  CircleDollarSign,
  Clock,
  Info,
  MoreHorizontal,
  Pencil,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable, CardHeading } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtDoc, fmtInt, fmtMoney, fmtPct, fmtSigned } from '../../lib/format';
import { BulkActionsMenu } from '../../components/BulkActionsMenu';
import { buildResultsBulkActions } from '../lib/decisionBulkActions';
import type { RankFactor, ReorderRecommendation } from '../types/reorder.types';
import type { RecDecision } from '../types/decisions.types';

const numMeta = { headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' };

const FACTOR_LABEL: Record<RankFactor['key'], string> = {
  urgency: 'Urgency',
  margin: 'Margin',
  abc: 'ABC value',
  priority: 'SO priority',
  committed: 'Committed vs forecast',
};

/** Days-to-stockout risk badge — sooner = more urgent (red < 7, amber < 21). */
export function StockoutRiskBadge({ days }: { days: number | null }) {
  if (days === null) return <span className="text-muted-foreground">{EM_DASH}</span>;
  const variant = days < 7 ? 'destructive' : days < 21 ? 'warning' : 'secondary';
  return (
    <Badge
      variant={variant}
      appearance="light"
      size="md"
      title={`Runs out in about ${days} day${days === 1 ? '' : 's'} at forecast demand`}
    >
      <Clock className="size-3" />
      {days}d
    </Badge>
  );
}

/** Per-row decision state → status badge + which draft PO an accept landed in. */
function DecisionCell({ decision }: { decision: RecDecision | undefined }) {
  if (!decision || decision.status === 'proposed') {
    return <span className="text-xs text-muted-foreground">Pending</span>;
  }
  if (decision.status === 'dismissed') {
    return (
      <Badge variant="secondary" appearance="light" size="md">
        Rejected
      </Badge>
    );
  }
  const isAdjusted = decision.status === 'adjusted';
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <Badge variant={isAdjusted ? 'warning' : 'success'} appearance="light" size="md">
        {isAdjusted ? 'Adjusted' : 'Accepted'}
      </Badge>
      {decision.draft_po_number && decision.draft_po_id ? (
        <Link
          href={`/scm/purchase-orders/${decision.draft_po_id}`}
          onClick={(e) => e.stopPropagation()}
          className="truncate text-2xs font-medium text-primary hover:underline"
          title={`Open ${decision.draft_po_number}`}
        >
          → {decision.draft_po_number}
        </Link>
      ) : null}
    </div>
  );
}

/** Rank cell — the # plus a hover popover surfacing which factors fed the score
 *  and which dominated (explainability for a novice, M4-D14). */
function RankCell({ rec }: { rec: ReorderRecommendation }) {
  const factors = rec.rank_factors ?? [];
  const present = factors.filter((f) => f.present && f.value !== null);
  // The single largest weight·value contribution — the dominant driver.
  const dominant = present.reduce<RankFactor | null>(
    (top, f) => (top === null || f.weight * (f.value ?? 0) > top.weight * (top.value ?? 0) ? f : top),
    null,
  );
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          title="Why this rank"
        >
          <span className="tabular-nums font-medium">{rec.rank ?? EM_DASH}</span>
          <Info className="size-3 text-muted-foreground" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPrimitive.Portal>
        <PopoverContent align="start" collisionPadding={8} className="w-72 p-0">
          <div className="border-b px-3 py-2 text-xs font-medium">
            Rank {rec.rank} · score {rec.rank_score != null ? rec.rank_score.toFixed(2) : EM_DASH}
          </div>
          <div className="max-h-64 overflow-y-auto py-1">
            {factors.map((f) => {
              const isDominant = dominant?.key === f.key;
              return (
                <div
                  key={f.key}
                  className={cn(
                    'flex items-center justify-between gap-3 px-3 py-1.5 text-sm',
                    !f.present && 'opacity-55',
                  )}
                >
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate">{FACTOR_LABEL[f.key]}</span>
                    {isDominant ? (
                      <Badge variant="primary" appearance="light" size="xs">
                        top
                      </Badge>
                    ) : null}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {f.present && f.value !== null ? (
                      <>
                        {fmtPct(f.value)} <span className="text-2xs">·w{f.weight}</span>
                      </>
                    ) : (
                      <span className="text-2xs italic">dropped — no cost</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </PopoverContent>
      </PopoverPrimitive.Portal>
    </Popover>
  );
}

/** Cash impact cell — "—" for an uncosted buy that can't be cash-ranked (M4-D16). */
function CashImpactCell({ rec }: { rec: ReorderRecommendation }) {
  if (rec.cash_impact === null) {
    return (
      <span
        className="text-muted-foreground"
        title="No supplier cost on file — add a cost to include this buy in cash ranking"
      >
        {EM_DASH}
      </span>
    );
  }
  return <span>{fmtMoney(rec.cash_impact)}</span>;
}

/** Row action menu — Accept / Adjust / Reject (M4-D7/D8). Rendered only when the
 *  decision callbacks are supplied (funded + deferred; never Needs cost). */
function RowActions({
  rec,
  decision,
  onAccept,
  onAdjust,
  onReject,
}: {
  rec: ReorderRecommendation;
  decision: RecDecision | undefined;
  onAccept: (rec: ReorderRecommendation) => void;
  onAdjust: (rec: ReorderRecommendation) => void;
  onReject: (rec: ReorderRecommendation) => void;
}) {
  const alreadyAccepted = decision?.status === 'accepted';
  return (
    <div className="flex items-center justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            className="h-8 w-8"
            onClick={(e) => e.stopPropagation()}
            aria-label="Row actions"
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem disabled={alreadyAccepted} onClick={() => onAccept(rec)}>
            <Check className="size-4" />
            {alreadyAccepted ? 'Accepted' : 'Accept'}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onAdjust(rec)}>
            <Pencil className="size-4" />
            Adjust…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive" onClick={() => onReject(rec)}>
            <X className="size-4" />
            Reject…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export function CashResultsGrid({
  rows,
  variant,
  isLoading,
  onRowClick,
  decisionsById,
  onAccept,
  onAdjust,
  onReject,
  onBulkAccept,
  onBulkReject,
  selectable = false,
}: {
  rows: ReorderRecommendation[];
  variant: 'funded' | 'deferred' | 'needs_cost';
  isLoading: boolean;
  onRowClick: (rec: ReorderRecommendation) => void;
  /** Decision state per recommendation id — enables the Decision + Actions columns. */
  decisionsById?: Record<string, RecDecision>;
  onAccept?: (rec: ReorderRecommendation) => void;
  onAdjust?: (rec: ReorderRecommendation) => void;
  onReject?: (rec: ReorderRecommendation) => void;
  /** Bulk Accept over the still-pending selected rows. Receives the pending recs
   *  plus a clear-selection callback the parent runs after a successful accept. */
  onBulkAccept?: (recs: ReorderRecommendation[], clearSelection: () => void) => void;
  /** Bulk Reject over the still-pending selected rows (same shape as onBulkAccept). */
  onBulkReject?: (recs: ReorderRecommendation[], clearSelection: () => void) => void;
  /** Adds selection checkboxes + a unified Actions toolbar strip. */
  selectable?: boolean;
}) {
  const isDeferred = variant === 'deferred';
  const isNeedsCost = variant === 'needs_cost';
  const decisionsEnabled = !!onAccept && !!onAdjust && !!onReject && !isNeedsCost;
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const columns = useMemo<ColumnDef<ReorderRecommendation>[]>(() => {
    const cols: ColumnDef<ReorderRecommendation>[] = [];

    if (selectable && decisionsEnabled) cols.push(buildSelectColumn<ReorderRecommendation>());

    // Rank is a CASH ordering — omitted for the un-priced "Needs cost" bucket.
    if (!isNeedsCost) {
      cols.push({
        accessorKey: 'rank',
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        cell: ({ row }) => <RankCell rec={row.original} />,
        size: 90,
        meta: { headerTitle: 'Rank', skeleton: <Skeleton className="h-5 w-10" /> },
      });
    }

    cols.push(
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="SKU" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="font-medium">{row.original.sku}</span>
            <span
              className="truncate text-xs text-muted-foreground"
              title={row.original.product_name}
            >
              {row.original.product_name}
            </span>
          </div>
        ),
        size: 220,
        meta: { headerTitle: 'SKU' },
      },
      {
        accessorKey: 'order_qty',
        header: ({ column }) => <DataGridColumnHeader title="Order qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.order_qty),
        size: 110,
        meta: { headerTitle: 'Order qty', ...numMeta },
      },
      {
        accessorKey: 'cash_impact',
        header: ({ column }) => <DataGridColumnHeader title="Cash impact" column={column} />,
        cell: ({ row }) => <CashImpactCell rec={row.original} />,
        size: 140,
        meta: { headerTitle: 'Cash impact', ...numMeta },
      },
      {
        accessorKey: 'net_position',
        header: ({ column }) => <DataGridColumnHeader title="Net" column={column} />,
        cell: ({ row }) => (
          <span className={cn((row.original.net_position ?? 0) < 0 && 'text-scm-stockout')}>
            {fmtSigned(row.original.net_position)}
          </span>
        ),
        size: 90,
        meta: { headerTitle: 'Net', ...numMeta },
      },
      {
        accessorKey: 'days_of_cover',
        header: ({ column }) => <DataGridColumnHeader title="Days cover" column={column} />,
        cell: ({ row }) => fmtDoc(row.original.days_of_cover, false),
        size: 110,
        meta: { headerTitle: 'Days cover', ...numMeta },
      },
      {
        accessorKey: 'supplier',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => {
          const s = row.original.supplier;
          if (!s) return <span className="text-muted-foreground">{EM_DASH}</span>;
          return (
            <div className="min-w-0">
              <div className="truncate font-medium" title={s.supplier_name}>
                {s.supplier_name}
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">
                {fmtMoney(s.unit_cost)} · {fmtInt(s.lead_time_days)}d lead
              </div>
            </div>
          );
        },
        size: 200,
        meta: { headerTitle: 'Supplier' },
      },
    );

    if (isDeferred) {
      cols.push({
        accessorKey: 'days_to_stockout',
        header: ({ column }) => <DataGridColumnHeader title="Stockout risk" column={column} />,
        cell: ({ row }) => <StockoutRiskBadge days={row.original.days_to_stockout} />,
        size: 140,
        meta: { headerTitle: 'Stockout risk' },
      });
    }

    if (decisionsEnabled) {
      cols.push(
        {
          id: 'decision',
          header: ({ column }) => <DataGridColumnHeader title="Decision" column={column} />,
          cell: ({ row }) => <DecisionCell decision={decisionsById?.[row.original.id]} />,
          size: 150,
          enableSorting: false,
          meta: { headerTitle: 'Decision' },
        },
        {
          id: 'actions',
          header: '',
          cell: ({ row }) => (
            <RowActions
              rec={row.original}
              decision={decisionsById?.[row.original.id]}
              onAccept={onAccept!}
              onAdjust={onAdjust!}
              onReject={onReject!}
            />
          ),
          size: 60,
          enableHiding: false,
          enableSorting: false,
        },
      );
    }

    return cols;
  }, [isDeferred, isNeedsCost, selectable, decisionsEnabled, decisionsById, onAccept, onAdjust, onReject]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    enableRowSelection: selectable && decisionsEnabled,
    state: selectable && decisionsEnabled ? { rowSelection } : undefined,
    onRowSelectionChange: selectable && decisionsEnabled ? setRowSelection : undefined,
  });

  const accentClass = isNeedsCost
    ? 'text-muted-foreground'
    : isDeferred
      ? 'text-scm-overstock'
      : 'text-scm-incoming';
  const title = isNeedsCost ? 'Needs cost' : isDeferred ? 'Deferred' : 'Funded';
  const HeadingIcon = isNeedsCost ? CircleDollarSign : isDeferred ? Clock : CheckCircle2;
  const emptyMessage = isNeedsCost
    ? 'Every buy has a supplier cost — nothing here.'
    : isDeferred
      ? 'Nothing deferred — the budget funds every costed buy.'
      : 'Nothing funded at this budget. Slide it up to fund the top-ranked buys.';

  const heading = (
    <CardHeading>
      <div className="flex items-center gap-2">
        <HeadingIcon className={cn('size-4', accentClass)} aria-hidden />
        <span className="text-sm font-semibold">{title}</span>
        <Badge variant="secondary" appearance="light" size="sm">
          {fmtInt(rows.length)}
        </Badge>
      </div>
    </CardHeading>
  );

  // The still-PENDING subset of the current selection — the only rows a bulk
  // Accept/Reject applies to (M4-D9). Actions gate off this count.
  const clearSelection = () => table.resetRowSelection();
  const pendingSelected = table
    .getSelectedRowModel()
    .rows.map((r) => r.original)
    .filter((rec) => {
      const st = decisionsById?.[rec.id]?.status;
      return !st || st === 'proposed';
    });

  const bulkActions = buildResultsBulkActions(
    { pendingCount: pendingSelected.length },
    {
      onAccept: () => onBulkAccept?.(pendingSelected, clearSelection),
      onReject: () => onBulkReject?.(pendingSelected, clearSelection),
    },
  );

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={emptyMessage}
      listingKey=""
      onRowClick={(row) => {
        (document.activeElement as HTMLElement | null)?.blur();
        onRowClick(row);
      }}
    >
      <Card>
        <CardHeader className="block">
          {selectable && decisionsEnabled ? (
            <DataGridListToolbar
              table={table}
              searchSlot={heading}
              exportConfig={false}
              showColumns={false}
              bulkActionsSlot={<BulkActionsMenu actions={bulkActions} />}
            />
          ) : (
            <>
              {heading}
              {isNeedsCost ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  These buys have no supplier cost, so they can&apos;t be cash-ranked. Add a supplier
                  cost to include them in funding.
                </p>
              ) : null}
            </>
          )}
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
      </Card>
    </DataGrid>
  );
}
