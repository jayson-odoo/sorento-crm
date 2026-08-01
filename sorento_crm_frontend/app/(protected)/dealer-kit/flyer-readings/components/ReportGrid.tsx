'use client';

import { useState, type ReactNode } from 'react';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
} from '@tanstack/react-table';

import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

export interface ReportGridProps<T extends object> {
  columns: ColumnDef<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  /** Rendered in place of the table when there is nothing to list. */
  emptyMessage: ReactNode;
  pageSize?: number;
  'data-testid'?: string;
}

/**
 * One report table, with the listing rules applied once instead of three times.
 *
 * The review screen lists three different things - codes the master does not
 * have, codes the promotion does not carry, sizes the flyer prints - and every
 * one of them is a listing, so every one of them owes the DataGrid contract a
 * fixed layout, resizable columns and an explicit size per column. Copying that
 * three times is three places for it to drift.
 *
 * Client-side paged on purpose: the whole report arrives in one response
 * (matching is a single recomputed pass over the reading), so paging it at the
 * server would be a second round trip for data already in the browser.
 */
export function ReportGrid<T extends object>({
  columns,
  rows,
  getRowId,
  emptyMessage,
  pageSize = 10,
  'data-testid': testId,
}: ReportGridProps<T>) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize });

  const table = useReactTable({
    columns,
    data: rows,
    getRowId,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      standardToolbar={false}
      // Column personalisation OFF, deliberately. Left unset the grid keys its
      // saved widths on the URL, which here carries a reading id - a per-user
      // config row per flyer, four of them per screen, none of it ever read
      // again. It also leaves the grid in its skeleton state until something
      // else re-renders it, so an empty section shows ten blank rows instead of
      // saying it is empty.
      listingKey=""
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={emptyMessage}
    >
      <Card data-testid={testId}>
        <CardTable>
          {/* Wider than a phone, so it scrolls inside its own container rather
              than dragging the page sideways. */}
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>

        {rows.length > pageSize && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
