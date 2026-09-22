'use client';

import { useMemo, useState } from 'react';
import {
  ExpandedState,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardHeader, CardTable, CardFooter } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useTableDeepLinkHighlight } from '@/hooks/useTableDeepLinkHighlight';
import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { ReserveRequestsSection } from './ReserveRequestsSection';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

/** `PLAN-oi-header-list-detail.md`, AC-DP-03. */
const LISTING_KEY = 'projects.projects.view::order-inquiry-lines';

function lineMatches(row: OrderInquiryWorklistRow, needle: string): boolean {
  if (!needle) return true;
  const haystack = `${row.item_code ?? ''} ${row.product_name ?? ''}`.toLowerCase();
  return haystack.includes(needle.toLowerCase());
}

export function OrderInquiryLinesTab({
  inquiryId,
  lines,
  isLoading,
  rowSelection,
  onRowSelectionChange,
  canRequestReserve,
  canReserve,
}: {
  inquiryId: string;
  lines: OrderInquiryWorklistRow[];
  isLoading: boolean;
  rowSelection: RowSelectionState;
  onRowSelectionChange: (next: RowSelectionState) => void;
  canRequestReserve: boolean;
  canReserve: boolean;
}) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const columns = useOrderInquiryHeaderLinesColumns();

  // Cancelled lines are hidden here, same as the worklist (S5) - they carry no
  // instruction left to confirm or link, only a history the raise-cancel already told.
  const rows = useMemo(() => lines.filter((line) => line.state !== 'cancelled'), [lines]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection, globalFilter: search, expanded },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    onRowSelectionChange: (updater) =>
      onRowSelectionChange(
        typeof updater === 'function' ? updater(rowSelection) : updater,
      ),
    enableRowSelection: true,
    getColumnCanGlobalFilter: () => true,
    globalFilterFn: (row, _columnId, value) => lineMatches(row.original, String(value ?? '')),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-4/10/11/12): a link from the SO detail's
  // own "Order inquiry" cell lands on this exact row (`?row=<id>`).
  const deepLink = useTableDeepLinkHighlight(table, {
    paramName: 'row',
    rowId: (row: OrderInquiryWorklistRow) => row.id,
    currentSearch: search,
    clearSearch: () => setSearch(''),
    enabled: !isLoading,
  });

  return (
    <div className="space-y-4">
      <ReserveRequestsSection
        inquiryId={inquiryId}
        lines={lines}
        canRequest={canRequestReserve}
        canReserve={canReserve}
      />
      <DataGrid
        table={table}
        recordCount={table.getFilteredRowModel().rows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage={
          lines.length === 0 ? 'Nothing was raised on this order inquiry.' : 'No product matches that search.'
        }
        listingKey={LISTING_KEY}
        rowAttributes={deepLink.rowAttributes}
        rowClassName={deepLink.rowClassName}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Search product..."
                  className="w-56"
                />
              }
              exportConfig={false}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination sizes={[10, 25, 50]} />
          </CardFooter>
        </Card>
      </DataGrid>
    </div>
  );
}

export default OrderInquiryLinesTab;
