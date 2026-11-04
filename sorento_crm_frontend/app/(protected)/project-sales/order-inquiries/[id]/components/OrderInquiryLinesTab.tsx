'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { useSoLineAttachmentLookup } from '../../../_shared/hooks/useSoLineAttachments';
import { STATE_LABEL } from '../../../_shared/components/OrderInquiryVerbPill';
import { reserveStatusFrom } from '../../../_shared/lib/orderInquiryHeaderStatus';
import { DEFAULT_HIDDEN_COLUMNS } from '../../components/orderInquiryWorklistColumns';
import {
  StagedReserveEntry,
  useOrderInquiryHeaderLinesColumns,
} from './orderInquiryHeaderLinesColumns';
import {
  foldInquiryLines,
  lineOf,
  tickRowsOf,
  toLineRows,
  type OrderInquiryLine,
  type OrderInquiryLineRow,
} from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import type { LineSplitsPayload } from '../../../_shared/types/lineSplit.types';
import type { OrderInquiryReserveRequest } from '../../../_shared/services/orderInquiryReserveService';

/** `PLAN-oi-header-list-detail.md`, AC-DP-03. */
const LISTING_KEY = 'projects.projects.view::order-inquiry-lines';

const NO_REQUESTS: OrderInquiryReserveRequest[] = [];

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

// OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:15): the lines view lives in the URL, so prev/next
// OI (`useListPager` carries every `view_*` key) and a reload keep it. State is comma-joined,
// the way every other multi-select filter writes its URL; sort is `<column>:<asc|desc>`.
const VIEW_SEARCH_PARAM = 'view_q';
const VIEW_STATE_PARAM = 'view_state';
const VIEW_SORT_PARAM = 'view_sort';
/** A search writes the URL once typing pauses, not on every key (each write is a navigation). */
const SEARCH_URL_DELAY_MS = 300;
const STATE_FILTER_VALUES = new Set(STATE_FILTER_OPTIONS.map((option) => option.value));

function stateFilterFromUrl(raw: string | null): string[] | null {
  if (raw == null) return null;
  return raw.split(',').filter((value) => STATE_FILTER_VALUES.has(value));
}

function sortingFromUrl(raw: string | null): SortingState {
  if (!raw) return [];
  const [id, dir] = raw.split(':');
  return id ? [{ id, desc: dir === 'desc' }] : [];
}

function sortingToUrl(sorting: SortingState): string | null {
  const first = sorting[0];
  return first ? `${first.id}:${first.desc ? 'desc' : 'asc'}` : null;
}

function matchesStateFilter(row: OrderInquiryWorklistRow, selected: string[]): boolean {
  if (selected.length === 0) return true;
  return selected.some((value) => {
    if (value === RESERVE_REQUESTED_FILTER_VALUE) return row.reserve_state === 'requested';
    if (value === RESERVE_RESERVED_FILTER_VALUE) return row.reserve_state === 'reserved';
    if (value === RESERVE_DECLINED_FILTER_VALUE) return row.reserve_state === 'declined';
    return row.state === value;
  });
}

/** A line matches the State filter when any of its live rows does (G5: the line folds
 * every live row, so filtering on one row's state would hide the line's others). */
function lineMatchesStateFilter(line: OrderInquiryLine, selected: string[]): boolean {
  if (selected.length === 0) return true;
  return line.liveRows.some((row) => matchesStateFilter(row, selected));
}

/** Detail's selection is keyed by ROW id (every mutation takes row ids); the grid ticks
 * LINES. A line reads ticked when every one of its tick rows is (`tickRowsOf`: its live
 * rows, or its waiting used rows when it has none, review S2). */
function lineSelectionOf(
  lineRows: OrderInquiryLineRow[],
  rowSelection: RowSelectionState,
): RowSelectionState {
  const next: RowSelectionState = {};
  for (const lineRow of lineRows) {
    const ticked = tickRowsOf(lineOf(lineRow));
    if (ticked.length > 0 && ticked.every((row) => rowSelection[row.id])) {
      next[lineOf(lineRow).key] = true;
    }
  }
  return next;
}

/** A ticked line hands back its live row ids only, never a cancelled one, and a used one
 * only on a line whose only waiting rows are used (AC-ND-12, AC-ND-27, review S2). */
function rowSelectionOf(
  lineRows: OrderInquiryLineRow[],
  lineSelection: RowSelectionState,
): RowSelectionState {
  const next: RowSelectionState = {};
  for (const lineRow of lineRows) {
    const line = lineOf(lineRow);
    if (!lineSelection[line.key]) continue;
    for (const row of tickRowsOf(line)) next[row.id] = true;
  }
  return next;
}

export function OrderInquiryLinesTab({
  lines,
  isLoading,
  error,
  onRetry,
  rowSelection,
  onRowSelectionChange,
  canReserve,
  stagedByRowId,
  onTickReserve,
  onRejectReserve,
  onEditReserve,
  onAmendReserve,
  onLineHistoryClick,
  onUndoStaged,
  canEditAttachments,
  decideSlot,
  splitSheet,
  reserveRequests = NO_REQUESTS,
}: {
  lines: OrderInquiryWorklistRow[];
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  rowSelection: RowSelectionState;
  onRowSelectionChange: (next: RowSelectionState) => void;
  /** AC-RS-83 (`PLAN-oi-request-cs-reserve.md` 6e.2): gates the Lines grid's own
   * reserve icons inside the State cell (AC-RS-83c) - the rest are their callbacks,
   * threaded straight through to `useOrderInquiryHeaderLinesColumns`. */
  canReserve?: boolean;
  stagedByRowId?: Record<string, StagedReserveEntry>;
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  /** OI-BULK-RESERVE (AC-BR-09): the line's x Reject. */
  onRejectReserve?: (row: OrderInquiryWorklistRow) => void;
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-ND-13/14: the line's one History icon. */
  onLineHistoryClick?: (line: OrderInquiryLine) => void;
  onUndoStaged?: (rowId: string) => void;
  /** #1312 (Q6): `projects.projects.edit` - gates the State cell's own paperclip
   * upload/remove, resolved by the caller (`OrderInquiryDetail.tsx`). */
  canEditAttachments?: boolean;
  /** OI-BULK-RESERVE (AC-BR-01): the caller's "Decide (N)", at the toolbar's right end
   * (its primary slot) so it sits right of the selection strip at 375 and 1280 alike. */
  decideSlot?: ReactNode;
  /** OI-SPLIT-VIEW (UAC E5): the order's split sheet for the Split column's line popups. */
  splitSheet?: {
    payload: LineSplitsPayload | null | undefined;
    error?: unknown;
    onRetry?: () => void;
  };
  /** OI-RESERVE-ROUND: this OI's reserve requests; feeds the Request filter, which a
   * one-OI email link (`?reserve=<id>[,<id>]`) ticks. */
  reserveRequests?: OrderInquiryReserveRequest[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>(() =>
    sortingFromUrl(searchParams.get(VIEW_SORT_PARAM)),
  );
  const [search, setSearchState] = useState(() => searchParams.get(VIEW_SEARCH_PARAM) ?? '');
  const [expanded, setExpanded] = useState<ExpandedState>({});
  // `?reserve=` holds a list status (written by the list) or request ids (written by the
  // one-OI email link). A status that still needs an answer preselects "Request to reserve"
  // (never `reserved` / `notice_parked`, AC-RF-83); request ids tick the Request filter and
  // leave State empty, so that request's lines show in every state (OI-RESERVE-ROUND).
  // A `view_state` the reader chose themselves (carried from the previous OI) wins.
  const [stateFilter, setStateFilter] = useState<string[]>(() => {
    const fromView = stateFilterFromUrl(searchParams.get(VIEW_STATE_PARAM));
    if (fromView) return fromView;
    const reserve = searchParams.get('reserve');
    return reserveStatusFrom(reserve) && reserve !== 'reserved' && reserve !== 'notice_parked'
      ? [RESERVE_REQUESTED_FILTER_VALUE]
      : [];
  });
  // The raw ids are kept and intersected with the requests at filter time: the requests
  // arrive after the first render, and an id that is not one of this OI's narrows nothing.
  const [requestIds, setRequestIds] = useState<string[]>(() => {
    const reserve = searchParams.get('reserve');
    return reserve && !reserveStatusFrom(reserve) ? reserve.split(',').filter(Boolean) : [];
  });
  const requestFilter = useMemo(
    () => requestIds.filter((id) => reserveRequests.some((request) => request.id === id)),
    [requestIds, reserveRequests],
  );
  const requestOptions = useMemo<SearchableMultiSelectOption[]>(
    () =>
      [...reserveRequests]
        .sort((a, b) => a.ordinal - b.ordinal)
        .map((request) => ({ value: request.id, label: `Request #${request.ordinal}` })),
    [reserveRequests],
  );
  const requestRowIds = useMemo(() => {
    const ids = new Set<string>();
    for (const request of reserveRequests) {
      if (requestFilter.includes(request.id)) for (const row of request.rows) ids.add(row.row_id);
    }
    return ids;
  }, [reserveRequests, requestFilter]);

  // The URL as it stands NOW, for a write that fires after a delay.
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
  }, []);

  /** Rewrites the lines-view params, keeping every other param (list state, tab, row). */
  function writeView(patch: Record<string, string | null>, drop: string[] = []) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    for (const key of drop) params.delete(key);
    for (const [key, value] of Object.entries(patch)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  function setSearch(next: string) {
    setSearchState(next);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(
      () => writeView({ [VIEW_SEARCH_PARAM]: next.trim() ? next : null }),
      SEARCH_URL_DELAY_MS,
    );
  }
  // #1312 (AC-U6): ONE lookup call for every line's attachments, never one per row -
  // the same shape the fulfilment board's own list view reads.
  const attachmentLineIds = useMemo(
    () => lines.map((row) => row.core_line_id).filter((id): id is string => Boolean(id)),
    [lines],
  );
  const { data: attachmentsByLine } = useSoLineAttachmentLookup(attachmentLineIds);
  const columns = useOrderInquiryHeaderLinesColumns({
    canReserve,
    stagedByRowId,
    onTickReserve,
    onRejectReserve,
    onEditReserve,
    onAmendReserve,
    onLineHistoryClick,
    onUndoStaged,
    attachmentsByLine,
    canEditAttachments,
    splitSheet,
  });

  // The param is dropped the moment the reader touches a filter themselves - it has done
  // its one job (preselecting) and must not keep re-forcing that selection back on every
  // unrelated re-render. A list status is the list's own filter and stays, so the pager keeps
  // its list (AC-RF-81).
  function requestParamToDrop(): string[] {
    const reserve = searchParams.get('reserve');
    return reserve && !reserveStatusFrom(reserve) ? ['reserve'] : [];
  }

  function handleSortingChange(updater: SortingState | ((old: SortingState) => SortingState)) {
    const next = typeof updater === 'function' ? updater(sorting) : updater;
    setSorting(next);
    writeView({ [VIEW_SORT_PARAM]: sortingToUrl(next) });
  }

  function handleStateFilterChange(next: string[]) {
    setStateFilter(next);
    // OI-UX-FILTER-SNAPSHOT: the State pick rides the URL as `view_state` (prev/next keeps it).
    writeView({ [VIEW_STATE_PARAM]: next.length ? next.join(',') : null }, requestParamToDrop());
  }

  function handleRequestFilterChange(next: string[]) {
    setRequestIds(next);
    // Request ids are this OI's own, so they never ride to the next OI as view state.
    const drop = requestParamToDrop();
    if (drop.length) writeView({}, drop);
  }

  // S0 (owner ruling 26 Sep, G5): ONE row per sales order line. S2 (AC-ND-20): `lines`
  // carries the header's cancelled rows too; the fold keeps them as their line's History
  // (G1) and never renders a line for them alone.
  const allLineRows = useMemo(() => toLineRows(foldInquiryLines(lines)), [lines]);
  const rows = useMemo(
    () =>
      allLineRows.filter(
        (lineRow) =>
          lineMatchesStateFilter(lineOf(lineRow), stateFilter) &&
          (requestFilter.length === 0 ||
            lineOf(lineRow).rows.some((row) => requestRowIds.has(row.id))),
      ),
    [allLineRows, stateFilter, requestFilter, requestRowIds],
  );
  const lineSelection = useMemo(
    () => lineSelectionOf(allLineRows, rowSelection),
    [allLineRows, rowSelection],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => lineOf(row).key,
    // AC-DT-6 (`PLAN-oi-decision-trail-ui.md`, round 2 ruling): "Raised via" is hidden by
    // default on THIS screen too now, matching the worklist's own `DEFAULT_HIDDEN_
    // COLUMNS` - `initialState` only, so a saved column preference (`listingKey` below)
    // still applies afterwards and wins.
    initialState: {
      columnVisibility: Object.fromEntries(
        DEFAULT_HIDDEN_COLUMNS.map((id) => [id, false]),
      ),
    },
    state: { pagination, sorting, rowSelection: lineSelection, globalFilter: search, expanded },
    onPaginationChange: setPagination,
    onSortingChange: handleSortingChange,
    onExpandedChange: setExpanded,
    onRowSelectionChange: (updater) =>
      onRowSelectionChange(
        rowSelectionOf(
          allLineRows,
          typeof updater === 'function' ? updater(lineSelection) : updater,
        ),
      ),
    // AC-ND-12: a line with no live row has nothing to confirm or link - unless a used row
    // on it still waits on Confirm (review S2).
    enableRowSelection: (row) => tickRowsOf(lineOf(row.original)).length > 0,
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
  // own "Order inquiry" cell lands on this exact row (`?row=<id>`). S0: the row now sits
  // inside its line, so the line answers to the id of ANY row it folds.
  const deepLinkTarget = searchParams.get('row');
  const deepLink = useTableDeepLinkHighlight(table, {
    paramName: 'row',
    rowId: (row: OrderInquiryLineRow) =>
      deepLinkTarget && lineOf(row).rows.some((r) => r.id === deepLinkTarget)
        ? deepLinkTarget
        : row.id,
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
      error={error}
      onRetry={onRetry}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        allLineRows.length === 0
          ? 'Nothing was raised on this order inquiry.'
          : (stateFilter.length > 0 || requestFilter.length > 0) && rows.length === 0
            ? 'No line matches the filter.'
            : 'No product matches that search.'
      }
      listingKey={LISTING_KEY}
      rowAttributes={deepLink.rowAttributes}
      // G7 / O2: a cancelled line and a line with nothing left to buy read muted, the
      // same `opacity-60` the worklist uses for a used or cancelled-line row.
      rowClassName={(row) =>
        [deepLink.rowClassName(row), lineOf(row).muted ? 'opacity-60' : null]
          .filter(Boolean)
          .join(' ') || undefined
      }
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
                    clearable
                  />
                </div>
                {reserveRequests.length > 0 ? (
                  <div className="flex items-center gap-1.5">
                    <Label htmlFor="oi-lines-request-filter" className="sr-only">
                      Request
                    </Label>
                    <SearchableMultiSelect
                      id="oi-lines-request-filter"
                      value={requestFilter}
                      onChange={handleRequestFilterChange}
                      options={requestOptions}
                      placeholder="Request"
                      className="w-40"
                      clearable
                    />
                  </div>
                ) : null}
              </div>
            }
            exportConfig={false}
            primaryAction={decideSlot}
            alignActionsEnd
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
