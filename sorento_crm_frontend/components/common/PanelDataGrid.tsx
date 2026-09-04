'use client';

import * as React from 'react';
import {
  ColumnDef,
  ExpandedState,
  OnChangeFn,
  PaginationState,
  Row,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  getExpandedRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * The system list, inside a detail tab.
 *
 * Every tab on a project or lead was showing its rows a different way: a `ul` with a
 * divider here, a grid of bordered cards there, a bespoke timeline somewhere else. The
 * client's words: "use our system design principle for the list" and "don't use this out
 * of system design punya list". A record read as a card in one tab and a row in the next
 * teaches nothing that carries over.
 *
 * So all of them render THIS, which is the same `DataGrid` the top-level listings use, with
 * the contract from ARCHITECTURE-RULES already applied: fixed table layout, resizable
 * columns, `onChange` resize mode, and the same pagination bar as the user list -- "1 - 1 of 1",
 * a page picker and a rows-per-page selector, shown WHENEVER there are rows. It was previously
 * hidden below one page, which is exactly what made a short list look like a different component
 * from the long one. Callers supply columns with explicit sizes, and nothing else.
 *
 * The row is the way in (ADR 1d), so pass `onRowClick` rather than adding an action column.
 */
export function PanelDataGrid<TRow extends object>({
  title,
  toolbar,
  columns,
  rows,
  getRowId,
  listingKey,
  isLoading = false,
  error,
  emptyTitle,
  emptyBody,
  emptyAction,
  onRowClick,
  searchPlaceholder,
  searchOf,
  renderGroupHeader,
  sortable = false,
  rowSelection,
  onRowSelectionChange,
  enableRowSelection,
  expanded,
  onExpandedChange,
  pageSize = 10,
  paginate = true,
  scrollerMaxHeight,
}: {
  /**
   * A plain heading, or a heading with an embedded link (e.g. the record's own number).
   *
   * OPTIONAL, for a grid already titled by what it opened from: the stock drill expands
   * under a location row that names the product and the bin, and repeating that above the
   * columns pushed the headers a line and a half away from the row they explain (captain,
   * 30 August 2026). With no title, no toolbar and no search the card header is not
   * rendered at all, so the column headers sit directly under that row.
   */
  title?: React.ReactNode;
  /** Filters, view switches and the Add button. Sits in the card header beside the title. */
  toolbar?: React.ReactNode;
  columns: ColumnDef<TRow>[];
  rows: TRow[];
  getRowId?: (row: TRow) => string;
  /** Drives per-user column order and visibility. See docs/LISTING-COLUMN-PREFERENCES.md. */
  listingKey: string;
  isLoading?: boolean;
  error?: unknown;
  emptyTitle: string;
  /** One short line at most. A tab is not the place to explain the feature (ADR 1e). */
  emptyBody?: string;
  emptyAction?: React.ReactNode;
  onRowClick?: (row: TRow) => void;
  /** Shown in the search box. Omit both search props for a list too short to need one. */
  searchPlaceholder?: string;
  /**
   * The text a search matches against, per row. Client-side on purpose: a detail tab holds
   * one project's rows, so there is nothing to page through on the server, and filtering in
   * the browser answers instantly.
   */
  searchOf?: (row: TRow) => string;
  /**
   * A band heading rendered above a row when it opens a new section - the quotation's
   * "BILL NO 3 PAGE 15/4". Return null for a row that continues the band it is already in.
   * Passed straight to the shared grid, so bands are a rendering of the row order rather than
   * a second list living beside it.
   */
  renderGroupHeader?: (row: TRow, previousRow: TRow | null) => React.ReactNode | null;
  /**
   * Let the reader sort the rows, client-side.
   *
   * OPT-IN, and deliberately not the default: a panel holds one record's rows in a meaningful
   * order (the allocation ranking, the quotation's bill order), and turning sorting on
   * everywhere would put a live control on every header of fifteen existing panels that never
   * asked for one. The initial order is always the order the caller passed.
   */
  sortable?: boolean;
  /**
   * Row selection, for a panel that offers bulk actions.
   *
   * The STATE is the caller's, because the actions are: a panel that owns a selection but not
   * the verbs that act on it can only hand the selection back, which is the same thing with an
   * extra step. Pass `buildSelectColumn(...)` as the first column and render the strip in
   * `toolbar`, exactly as the users list does.
   */
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: React.Dispatch<React.SetStateAction<RowSelectionState>>;
  /** Which rows may be ticked. TanStack reads this from the TABLE, never from the column. */
  enableRowSelection?: (row: Row<TRow>) => boolean;
  /**
   * Which row is open in place, and the setter for it.
   *
   * The STATE is the caller's for the same reason the selection is: what the drawer holds
   * belongs to the screen that opened it, and a panel that owned the expansion but not the
   * editor inside it could only hand the row back. Pair it with `meta.expandedContent` on
   * one column - the shared `DataGridTable` renders that full-width under any expanded row -
   * and toggle it from `onRowClick`, the way reorder planning's `PlanLinesGrid` does.
   *
   * Opt-in: without it the expanded row model is never built, so fifteen existing panels
   * keep the exact table they have today.
   */
  expanded?: ExpandedState;
  onExpandedChange?: OnChangeFn<ExpandedState>;
  pageSize?: number;
  /**
   * SF-8 (M5 run 3 review): `false` renders every row and hides the pager - the
   * ruling for a line table ON A DOCUMENT (an order's own lines, a GRN's own
   * picking lines), where a page-2 hides rows the reader expects to see in one
   * scroll. Default `true` (the 10-row page every other panel keeps) is
   * unaffected - this is opt-in per caller, not a change to the shared default.
   */
  paginate?: boolean;
  /**
   * Pass `false` when the caller already renders this inside a `DialogBody` or
   * `SheetBody` that owns its own `overflow-y-auto` viewport (B2, M5 review run 1) -
   * without it the grid's own M5-05 bounded scroller nests a second scrollport
   * inside the first. Omit it for a plain detail-page tab panel, which wants the
   * default bounded, sticky-header scroller like every other list.
   */
  scrollerMaxHeight?: string | false;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    // `Number.MAX_SAFE_INTEGER`: TanStack's pagination row model slices by index,
    // so an oversized page size is just "every row", not a real second page.
    pageSize: paginate ? pageSize : Number.MAX_SAFE_INTEGER,
  });
  const [search, setSearch] = React.useState('');
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const filtered = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle || !searchOf) return rows;
    return rows.filter((row) => searchOf(row).toLowerCase().includes(needle));
  }, [rows, search, searchOf]);

  const table = useReactTable({
    columns: columns as ColumnDef<TRow, unknown>[],
    data: filtered,
    pageCount: Math.ceil(filtered.length / pagination.pageSize) || 0,
    getRowId,
    state: {
      pagination,
      ...(sortable ? { sorting } : {}),
      ...(rowSelection ? { rowSelection } : {}),
      ...(expanded === undefined ? {} : { expanded }),
    },
    ...(rowSelection
      ? {
          onRowSelectionChange,
          enableRowSelection: enableRowSelection ?? true,
        }
      : {}),
    onPaginationChange: setPagination,
    ...(sortable
      ? { onSortingChange: setSorting, getSortedRowModel: getSortedRowModel() }
      : { enableSorting: false }),
    ...(expanded === undefined
      ? {}
      : { onExpandedChange, getExpandedRowModel: getExpandedRowModel() }),
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={filtered.length}
      isLoading={isLoading}
      listingKey={listingKey}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        // Most callers are a plain detail-page tab and want M5-05's own bounded,
        // sticky-header scroller. A caller embedded in a `DialogBody`/`SheetBody`
        // that already owns the scroll viewport passes `false` here instead, or
        // that ancestor's own `overflow-y-auto` would double-bound it.
        scrollerMaxHeight,
      }}
      onRowClick={onRowClick}
      renderGroupHeader={renderGroupHeader as never}
    >
      <Card>
        {/* flex-col until sm so a title and a toolbar never overlap at phone width. Not
            rendered at all when there is nothing to put in it, so a grid titled by the row
            it expanded from starts at its own column headers. */}
        {(title || toolbar || searchOf) && (
          <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            {title ? (
              <CardTitle className="min-w-0 break-words text-sm">{title}</CardTitle>
            ) : null}
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
              {searchOf && (
                <Input
                  type="search"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    // Back to page one: filtering while on page three shows an empty table.
                    setPagination((current) => ({ ...current, pageIndex: 0 }));
                  }}
                  placeholder={searchPlaceholder ?? 'Search…'}
                  aria-label={searchPlaceholder ?? 'Search'}
                  className="h-8 w-full sm:w-56"
                />
              )}
              {toolbar}
            </div>
          </CardHeader>
        )}

        <CardTable>
          {error ? (
            <div className="px-6 py-10 text-center text-sm text-destructive">
              {error instanceof Error ? error.message : 'This list could not be loaded.'}
            </div>
          ) : isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : filtered.length === 0 ? (
            // Rendered rather than hidden, per the CRUD standard: a tab that vanishes when
            // empty makes the feature look absent instead of unused.
            <div className="px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">
                {rows.length > 0 ? 'Nothing matches that search' : emptyTitle}
              </h3>
              {emptyBody && (
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {emptyBody}
                </p>
              )}
              {emptyAction && <div className="mt-4 flex justify-center">{emptyAction}</div>}
            </div>
          ) : (
            <DataGridTable />
          )}
        </CardTable>

        {paginate && filtered.length > 0 && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
