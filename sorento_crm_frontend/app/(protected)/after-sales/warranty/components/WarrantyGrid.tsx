'use client';

import { useState, type ReactNode } from 'react';
import {
  ColumnDef,
  OnChangeFn,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar, type ListToolbarFilters } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { isSearchInFlight } from '@/hooks/useDebouncedSearch';

interface Props<T extends { id: string }> {
  rows: T[];
  total: number;
  columns: ColumnDef<T>[];
  pagination: PaginationState;
  onPaginationChange: OnChangeFn<PaginationState>;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  search: { value: string; onChange: (v: string) => void; settling: boolean; query: string; placeholder: string };
  isLoading: boolean;
  isFetching: boolean;
  isPlaceholderData?: boolean;
  error?: unknown;
  refetch: () => void;
  empty: { title: string; hint: string };
  filters?: ListToolbarFilters;
  leftActions?: ReactNode;
  primaryAction?: ReactNode;
  rowHref?: (row: T) => string;
  /** The context menu's items for a row; omit for no menu. */
  menu?: (row: T) => ReactNode;
}

/** The shared list shape of the Warranty Configuration tabs: one toolbar row, a fixed-layout DataGrid, a right-click row menu. */
export default function WarrantyGrid<T extends { id: string }>({
  rows,
  total,
  columns,
  pagination,
  onPaginationChange,
  sorting,
  onSortingChange,
  search,
  isLoading,
  isFetching,
  isPlaceholderData,
  error,
  refetch,
  empty,
  filters,
  leftActions,
  primaryAction,
  rowHref,
  menu,
}: Props<T>) {
  const [menuRow, setMenuRow] = useState<T | null>(null);
  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange,
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  return (
    <ContextMenu modal={false}>
      <ContextMenuTrigger asChild>
        <div
          // Capture phase: a right-click outside a row stops here, so the browser's own menu shows.
          onContextMenuCapture={(event) => {
            const el = (event.target as Element).closest('[data-row-id]');
            const row = rows.find((r) => r.id === el?.getAttribute('data-row-id'));
            if (!menu || !row) {
              event.stopPropagation();
              return;
            }
            setMenuRow(row);
          }}
        >
          <DataGrid
            table={table}
            recordCount={total}
            isLoading={isLoading}
            isPlaceholderData={isPlaceholderData}
            error={error}
            onRetry={refetch}
            rowHref={rowHref}
            rowAttributes={(row) => ({ 'data-row-id': row.id })}
            emptyMessage={
              <div className="py-4 text-center">
                <h3 className="text-sm font-medium">{empty.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{empty.hint}</p>
              </div>
            }
            standardToolbar={false}
            tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
          >
            <Card>
              <CardHeader className="block">
                <DataGridListToolbar
                  table={table}
                  searchSlot={
                    <ListSearchInput
                      value={search.value}
                      onChange={search.onChange}
                      isSettling={isSearchInFlight(search.settling, isFetching, search.query)}
                      placeholder={search.placeholder}
                      className="w-64"
                    />
                  }
                  filters={filters}
                  leftActions={leftActions}
                  onRefresh={refetch}
                  isRefreshing={isFetching && !isLoading}
                  primaryAction={primaryAction}
                />
              </CardHeader>
              <CardTable>
                <DataGridTable />
              </CardTable>
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
            </Card>
          </DataGrid>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-52">{menuRow && menu ? menu(menuRow) : null}</ContextMenuContent>
    </ContextMenu>
  );
}
