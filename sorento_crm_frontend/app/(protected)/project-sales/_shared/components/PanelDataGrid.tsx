'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
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
  pageSize = 10,
}: {
  title: string;
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
  pageSize?: number;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize,
  });
  const [search, setSearch] = React.useState('');

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
    state: { pagination },
    onPaginationChange: setPagination,
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
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      onRowClick={onRowClick}
      renderGroupHeader={renderGroupHeader as never}
    >
      <Card>
        {/* flex-col until sm so a title and a toolbar never overlap at phone width. */}
        <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words text-sm">{title}</CardTitle>
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
                aria-label={searchPlaceholder ?? `Search ${title}`}
                className="h-8 w-full sm:w-56"
              />
            )}
            {toolbar}
          </div>
        </CardHeader>

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
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>

        {filtered.length > 0 && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
