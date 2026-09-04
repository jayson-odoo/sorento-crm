'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useStockDebtQuery } from '../hooks/useStockDebtQuery';
import type { StockDebtRow, StockDebtTone } from '../types/stockDebt.types';
import { StockDebtCellDialog } from './StockDebtCellDialog';

/**
 * Stock Debt: one row per product, one column per month, and the cell is that MONTH's own
 * balance (R37, AC-S2-10) - the supply dated in it that stayed free, less what the lines
 * due in it went short of on their own dates. What is debted in August stays in August; a
 * month with nothing due and nothing arriving reads 0.
 *
 * The view shows and never decides (R23). A cell is a way into the two tables behind
 * it - the demand due and the supply held - and each demand line's Plan press hands
 * the order to the board, which is where deciding happens.
 *
 * The screen carries no explanation of what a colour means: the tone is a reading of
 * the number beside it, and a legend on a planner's daily screen is a paragraph they
 * read once (cursor rule: no feature explanations in the UI).
 */

/** Cell tone as a CLASS, not a component (plan 3.4): three lines, no new file. */
const TONE_CLASS: Record<StockDebtTone, string> = {
  red: 'bg-destructive/10 text-destructive',
  amber: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  green: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
};

/**
 * TBA and No date carry no tone: they draw no supply at all (R14), so a colour that
 * elsewhere means "can this still be bought in time" would be answering a question
 * nobody asked of them. Informational, per the plan's tone card.
 */
const NEUTRAL_CLASS = 'bg-muted text-foreground';

/** `2026-08` -> `Aug 26`. Narrow on purpose: fifteen of these share one width. */
function monthLabel(key: string): string {
  const [year, month] = key.split('-');
  const index = Number(month) - 1;
  const names = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  return `${names[index] ?? month} ${year?.slice(2) ?? ''}`;
}

/** `-16` reads as debt, `+84` as surplus; a bare `84` reads as neither. */
function signed(value: number): string {
  return value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString();
}

/** Which cell is open. `month` is a `YYYY-MM` key, or `tba` / `undated`. */
interface OpenCell {
  productId: string;
  productCode: string;
  productName: string | null;
  month: string;
  label: string;
  balance: number;
}

export function StockDebtClient() {
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debounced,
    isSettling: debouncedSettling,
  } = useDebouncedSearch();
  const [group, setGroup] = React.useState('');
  // Default ON (AC-S2-10): the whole catalogue is ~4,000 products and the answer the
  // planner came for is the short list that owes something.
  const [onlyDebt, setOnlyDebt] = React.useState(true);
  const [openCell, setOpenCell] = React.useState<OpenCell | null>(null);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  // Narrowing changes which rows exist, so page 3 of the old set is a page of nothing.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debounced, group, onlyDebt]);

  const list = useStockDebtQuery({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    query: debounced,
    group,
    onlyDebt,
  });

  const rows = list.data?.data ?? [];
  const total = list.data?.pagination.total ?? 0;
  const months = React.useMemo(() => list.data?.months ?? [], [list.data]);
  const tbaMonth = list.data?.tba_month ?? null;
  const groups = list.data?.groups ?? [];

  const columns = React.useMemo<ColumnDef<StockDebtRow>[]>(() => {
    const openFor = (
      row: StockDebtRow,
      month: string,
      label: string,
      balance: number,
    ) =>
      setOpenCell({
        productId: row.product_id,
        productCode: row.product_code,
        productName: row.product_name,
        month,
        label,
        balance,
      });

    /** Every cell is a press, TBA and No date included (R28). */
    const cell = (
      row: StockDebtRow,
      month: string,
      label: string,
      balance: number,
      toneClass: string,
    ) => (
      <button
        type="button"
        onClick={() => openFor(row, month, label, balance)}
        title={`${row.product_code} - ${label}: ${signed(balance)}`}
        aria-label={`${row.product_code}, ${label}, balance ${signed(balance)}`}
        className={cn(
          'block w-full rounded px-2 py-1 text-end text-sm tabular-nums transition-colors hover:brightness-95 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          toneClass,
        )}
      >
        {signed(balance)}
      </button>
    );

    return [
      {
        id: 'product',
        header: 'Product',
        // PINNED, not hand-stuck. The DataGrid's own column pinning
        // (`tableLayout.columnsPinnable` + `initialState.columnPinning`) writes
        // `position: sticky` and the `left` offset as an INLINE style, which is the only
        // way it holds: a `sticky left-0` utility in `headerClassName` sits in the same
        // Tailwind position group as the `relative` the base cell already carries, and
        // which of the two wins is decided by their order in the generated stylesheet,
        // not by the order in the class attribute. It lost, and the column computed to
        // `position: relative` in the browser while reading as sticky in the source.
        meta: {
          headerTitle: 'Product',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
        size: 240,
        cell: ({ row }) => {
          const label = row.original.product_name
            ? `${row.original.product_code} - ${row.original.product_name}`
            : row.original.product_code;
          return (
            <div className="min-w-0" title={label}>
              <div className="truncate text-sm font-medium">
                {row.original.product_code}
              </div>
              {row.original.product_name && (
                <div className="truncate text-xs text-muted-foreground">
                  {row.original.product_name}
                </div>
              )}
            </div>
          );
        },
      },
      ...months.map<ColumnDef<StockDebtRow>>((key) => ({
        id: `m:${key}`,
        header: monthLabel(key),
        meta: {
          headerTitle: monthLabel(key),
          headerClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-full" />,
        },
        size: 96,
        cell: ({ row }) => {
          const month = row.original.months.find((entry) => entry.key === key);
          if (!month) return <span className="block text-end text-muted-foreground">-</span>;
          return cell(
            row.original,
            key,
            monthLabel(key),
            month.balance,
            TONE_CLASS[month.tone],
          );
        },
      })),
      {
        id: 'tba',
        // The policy's own TBA month is the label, so the column names the date the
        // book actually uses rather than a hard-coded 2030.
        header: tbaMonth ?? 'TBA',
        meta: {
          headerTitle: tbaMonth ?? 'TBA',
          headerClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-full" />,
        },
        size: 104,
        cell: ({ row }) =>
          cell(
            row.original,
            'tba',
            tbaMonth ?? 'TBA',
            row.original.tba,
            NEUTRAL_CLASS,
          ),
      },
      {
        id: 'undated',
        header: 'No date',
        meta: {
          headerTitle: 'No date',
          headerClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-full" />,
        },
        size: 104,
        cell: ({ row }) =>
          cell(row.original, 'undated', 'No date', row.original.undated, NEUTRAL_CLASS),
      },
      {
        id: 'unlocated',
        // Demand booked at no warehouse. It is in no group's pile, so it draws nothing and
        // sits in no month - stated here rather than dropped, because a screen that lists
        // what is owed and quietly omits it answers a narrower question than it is asked.
        header: 'No location',
        meta: {
          headerTitle: 'No location',
          headerClassName: 'text-end',
          skeleton: <Skeleton className="h-4 w-full" />,
        },
        size: 116,
        cell: ({ row }) =>
          cell(
            row.original,
            'unlocated',
            'No location',
            row.original.unlocated,
            NEUTRAL_CLASS,
          ),
      },
    ];
  }, [months, tbaMonth]);

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.product_id,
    // The product column is pinned left for the life of the screen; nothing on the toolbar
    // can unpin it, so it is initial state rather than controlled state with no setter.
    initialState: { columnPinning: { left: ['product'] } },
    state: { pagination },
    onPaginationChange: setPagination,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    manualPagination: true,
    enableSorting: false,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const filtered = Boolean(debounced || group);

  return (
    // `min-w-0` so the grid's own horizontal scroll stays INSIDE the card: without it
    // the wide table pushes the page body sideways and the sidebar goes with it (AC-S2-12).
    <div className="min-w-0 space-y-4">
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={list.isLoading}
        isPlaceholderData={list.isPlaceholderData}
        listingKey={null}
        // `listingKey={null}`: the columns ARE the months, so a stored order or visibility
        // would pin an axis that moves on the first of every month. Nothing to persist -
        // and it has to be said out loud, because omitting the prop makes the grid persist
        // under the PATHNAME instead. A row saved that way was re-applied against the
        // columns that existed the moment it arrived, which walked the three no-supply
        // columns up next to Product and left TanStack warning about months not yet built.
        // `columnsDraggable: false` is load-bearing, not tidiness. The DataGrid defaults
        // it to TRUE, and in that mode every cell gets `position: relative` as an INLINE
        // style from dnd-kit and the table drops `border-separate border-spacing-0` - so a
        // pinned column cannot stick however it is spelled. Reordering is meaningless here
        // anyway: the columns are the calendar (which is also why there is no `listingKey`).
        tableLayout={{
          width: 'fixed',
          columnsResizable: true,
          columnsPinnable: true,
          columnsDraggable: false,
        }}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-semibold">
              {filtered ? 'No product matches' : 'No product is in debt'}
            </p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {filtered
                ? 'Clear the search and the group to see the whole book.'
                : 'Every product covers its orders from stock already held or already on the way.'}
            </p>
            {onlyDebt && (
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => setOnlyDebt(false)}
              >
                Show every product
              </Button>
            )}
          </div>
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              // Nothing to personalise while the axis is the calendar (see above), and
              // no selection to export: this table is a reading, not a worklist.
              showColumns={false}
              exportConfig={false}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  isSettling={isSearchInFlight(debouncedSettling, list.isFetching, debounced)}
                  placeholder="Search product code or name…"
                  aria-label="Search products"
                  className="w-full max-w-xs"
                />
              }
              filters={{
                kind: 'custom',
                active: Boolean(group),
                activeCount: group ? 1 : 0,
                activeSummary: group
                  ? { label: `Group ${group}`, onClear: () => setGroup('') }
                  : undefined,
                content: (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      Ownership group
                    </Label>
                    <SearchableSelect
                      value={group}
                      onChange={setGroup}
                      clearable
                      options={groups.map((entry) => ({
                        value: entry,
                        label: entry,
                      }))}
                      placeholder="Every group"
                    />
                  </div>
                ),
              }}
              leftActions={
                <div className="flex items-center gap-2">
                  <Switch
                    id="only-debt"
                    checked={onlyDebt}
                    onCheckedChange={setOnlyDebt}
                  />
                  <Label htmlFor="only-debt" className="text-sm whitespace-nowrap">
                    Only products in debt
                  </Label>
                </div>
              }
              onRefresh={() => void list.refetch()}
              isRefreshing={list.isFetching && !list.isLoading}
            />
          </CardHeader>
          <CardTable>
            {list.isError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
                <h2 className="text-sm font-semibold text-destructive">
                  Stock debt could not be loaded
                </h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {list.error instanceof Error
                    ? list.error.message
                    : 'Try again shortly.'}
                </p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => void list.refetch()}
                >
                  Retry
                </Button>
              </div>
            ) : (
              // A PLAIN overflow container, not the shared `ScrollArea`. Radix puts a
              // `display: table !important` wrapper inside its viewport, and a pinned cell
              // then sticks to a box that is as wide as its own content and never scrolls
              // out - so the column reads as pinned and moves anyway. `overscroll-x-contain`
              // keeps a sideways flick inside the grid, which is what stops the page body
              // scrolling horizontally at 375px (AC-S2-12); the same shape
              // `ContainerRequestScheduleMatrix` already uses for the same reason.
              <div className="relative w-full overflow-x-auto overscroll-x-contain">
                <DataGridTable />
              </div>
            )}
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      {openCell && (
        <StockDebtCellDialog
          productId={openCell.productId}
          productCode={openCell.productCode}
          productName={openCell.productName}
          month={openCell.month}
          monthLabel={openCell.label}
          balance={openCell.balance}
          group={group}
          onClose={() => setOpenCell(null)}
        />
      )}
    </div>
  );
}
