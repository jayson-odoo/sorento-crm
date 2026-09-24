'use client';

import { useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
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
import { Label } from '@/components/ui/label';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { useTableDeepLinkHighlight } from '@/hooks/useTableDeepLinkHighlight';
import { STATE_LABEL } from '../../../_shared/components/OrderInquiryVerbPill';
import {
  StagedReserveEntry,
  useOrderInquiryHeaderLinesColumns,
} from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

/** `PLAN-oi-header-list-detail.md`, AC-DP-03. */
const LISTING_KEY = 'projects.projects.view::order-inquiry-lines';

function lineMatches(row: OrderInquiryWorklistRow, needle: string): boolean {
  if (!needle) return true;
  const haystack = `${row.item_code ?? ''} ${row.product_name ?? ''}`.toLowerCase();
  return haystack.includes(needle.toLowerCase());
}

// AC-RS-88 (`PLAN-oi-request-cs-reserve.md` 6e.2): the two reserve-state values ride
// beside the plain `STATE_LABEL` ones in the SAME filter, never a second control, under
// their own namespaced values so they collide with nothing a real `state` holds.
// `cancelled` is not offered (6e.4, AC-RS-88b): this grid never shows a cancelled line.
const RESERVE_REQUESTED_FILTER_VALUE = 'reserve:requested';
const RESERVE_RESERVED_FILTER_VALUE = 'reserve:reserved';
const RESERVE_DECLINED_FILTER_VALUE = 'reserve:declined';

const STATE_FILTER_OPTIONS: SearchableMultiSelectOption[] = [
  { value: 'raised', label: STATE_LABEL.raised },
  { value: 'partly_linked', label: STATE_LABEL.partly_linked },
  { value: 'placed', label: STATE_LABEL.placed },
  { value: 'actioned', label: STATE_LABEL.actioned },
  { value: RESERVE_REQUESTED_FILTER_VALUE, label: 'Request to reserve' },
  { value: RESERVE_RESERVED_FILTER_VALUE, label: 'Reserved' },
  { value: RESERVE_DECLINED_FILTER_VALUE, label: 'Not reserved' },
];

function matchesStateFilter(row: OrderInquiryWorklistRow, selected: string[]): boolean {
  if (selected.length === 0) return true;
  return selected.some((value) => {
    if (value === RESERVE_REQUESTED_FILTER_VALUE) return row.reserve_state === 'requested';
    if (value === RESERVE_RESERVED_FILTER_VALUE) return row.reserve_state === 'reserved';
    if (value === RESERVE_DECLINED_FILTER_VALUE) return row.reserve_state === 'declined';
    return row.state === value;
  });
}

export function OrderInquiryLinesTab({
  lines,
  isLoading,
  rowSelection,
  onRowSelectionChange,
  canReserve,
  stagedByRowId,
  onTickReserve,
  onEditReserve,
  onAmendReserve,
  onHistoryClick,
  onUndoStaged,
}: {
  lines: OrderInquiryWorklistRow[];
  isLoading: boolean;
  rowSelection: RowSelectionState;
  onRowSelectionChange: (next: RowSelectionState) => void;
  /** AC-RS-83 (`PLAN-oi-request-cs-reserve.md` 6e.2): gates the Lines grid's own
   * `reserve_actions` icon-button column - the rest are that column's own callbacks,
   * threaded straight through to `useOrderInquiryHeaderLinesColumns`. */
  canReserve?: boolean;
  stagedByRowId?: Record<string, StagedReserveEntry>;
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  onHistoryClick?: (row: OrderInquiryWorklistRow) => void;
  onUndoStaged?: (rowId: string) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<ExpandedState>({});
  // AC-RS-88: `?reserve=<id>` preselects "Request to reserve" - never opens a dialog
  // any more (round 3's own deep-link dialog is retired).
  const [stateFilter, setStateFilter] = useState<string[]>(() =>
    searchParams.get('reserve') ? [RESERVE_REQUESTED_FILTER_VALUE] : [],
  );
  // 6e.4 (AC-RS-83b): the action column only when there is something to act on - a
  // line with an open request (`requested`) or an answered one (`reserved`/`declined`).
  const showReserveActions = useMemo(
    () =>
      lines.some(
        (line) =>
          line.reserve_state === 'requested' ||
          line.reserve_state === 'reserved' ||
          line.reserve_state === 'declined',
      ),
    [lines],
  );
  const columns = useOrderInquiryHeaderLinesColumns({
    canReserve,
    showReserveActions,
    stagedByRowId,
    onTickReserve,
    onEditReserve,
    onAmendReserve,
    onHistoryClick,
    onUndoStaged,
  });

  function handleStateFilterChange(next: string[]) {
    setStateFilter(next);
    // The param is dropped the moment the reader touches the filter themselves - it
    // has done its one job (preselecting) and must not keep re-forcing that selection
    // back on every unrelated re-render.
    if (searchParams.get('reserve')) {
      const params = new URLSearchParams(searchParams.toString());
      params.delete('reserve');
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    }
  }

  // Cancelled lines are hidden here, same as the worklist (S5) - they carry no
  // instruction left to confirm or link, only a history the raise-cancel already told.
  const rows = useMemo(
    () =>
      lines
        .filter((line) => line.state !== 'cancelled')
        .filter((line) => matchesStateFilter(line, stateFilter)),
    [lines, stateFilter],
  );

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
    // N3 (reviewer round): this used to be wrapped in an orphan `<div
    // className="space-y-4">` - one child, so the spacing utility did nothing.
    <DataGrid
      table={table}
      recordCount={table.getFilteredRowModel().rows.length}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        lines.length === 0
          ? 'Nothing was raised on this order inquiry.'
          : stateFilter.length > 0 && rows.length === 0
            ? 'No line matches the filter.'
            : 'No product matches that search.'
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
              <div className="flex flex-wrap items-center gap-2">
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Search product..."
                  className="w-56"
                />
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="oi-lines-state-filter" className="sr-only">
                    State
                  </Label>
                  <SearchableMultiSelect
                    id="oi-lines-state-filter"
                    value={stateFilter}
                    onChange={handleStateFilterChange}
                    options={STATE_FILTER_OPTIONS}
                    placeholder="State"
                    className="w-48"
                  />
                </div>
              </div>
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
  );
}

export default OrderInquiryLinesTab;
