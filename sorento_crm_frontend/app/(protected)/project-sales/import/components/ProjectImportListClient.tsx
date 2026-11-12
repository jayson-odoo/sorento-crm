'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { formatDateSafe } from '@/lib/helpers';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { getUsersSelect } from '@/services/userSelectService';
import { RUN_PERMISSION, useProjectImportRuns } from '../../_shared/hooks/useProjectImport';
import type { ProjectImportRunRow } from '../../_shared/types/projectImport.types';
import { CreateImportDialog } from './CreateImportDialog';
import { RunStatusBadge, STATUS_LABELS } from './importLabels';

const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }));

function Num({ value }: { value: number }) {
  return <span className="tabular-nums">{value}</span>;
}

/** The runs list (AC-PI-43): the standard DataGrid, every column sorted on the server. */
export function ProjectImportListClient() {
  const router = useRouter();
  const [creating, setCreating] = React.useState(false);
  const canRun = useHasPermission(RUN_PERMISSION);
  const {
    value: search,
    setValue: setSearch,
    debouncedValue,
    isSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [pagination, setPagination] = React.useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'uploaded_at', desc: true }]);
  const [status, setStatus] = React.useState<string[]>([]);
  const [uploadedBy, setUploadedBy] = React.useState<string[]>([]);

  // A run opened from here carries this list's state in its URL (page, sort, search, filters),
  // so Back and prev/next walk the same list; landing here with that URL restores it.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting.length ? state.sorting : [{ id: 'uploaded_at', desc: true }]);
    resetSearch(state.searchQuery);
    setStatus(splitMulti(state.filters.status));
    setUploadedBy(splitMulti(state.filters.uploaded_by));
  });

  const grid = { ...pagination, sorting, searchQuery: debouncedValue };
  // The list keeps its whole state in the address bar as it changes (page, sort, search and
  // filters), so a reload or Back lands on the same list: the same query string a row click
  // carries to the run, written the way the contacts list does. Not on mount: the URL is the
  // input then, `useListStateFromUrl` has just read it.
  const listSearch = buildDetailSearch(grid, {
    status: status.length ? joinMulti(status) : undefined,
    uploaded_by: uploadedBy.length ? joinMulti(uploadedBy) : undefined,
  });
  const writtenSearch = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (writtenSearch.current === null) {
      writtenSearch.current = listSearch;
      return;
    }
    if (writtenSearch.current === listSearch) return;
    writtenSearch.current = listSearch;
    window.history.replaceState(
      window.history.state,
      '',
      `${window.location.pathname}${listSearch ? `?${listSearch}` : ''}`,
    );
  }, [listSearch]);

  const rowHref = (row: ProjectImportRunRow) => {
    const query = buildDetailSearch(grid, {
      status: status.length ? joinMulti(status) : undefined,
      uploaded_by: uploadedBy.length ? joinMulti(uploadedBy) : undefined,
      from: row.id,
    });
    return `/project-sales/import/${row.id}${query ? `?${query}` : ''}`;
  };
  const runs = useProjectImportRuns(grid, { status, uploaded_by: uploadedBy });
  const rows = runs.data?.data ?? [];
  const total = runs.data?.total ?? 0;
  const filtered = Boolean(debouncedValue || status.length || uploadedBy.length);

  useResetPageOnFilterChange(setPagination, [debouncedValue, status, uploadedBy]);

  const columns = React.useMemo<ColumnDef<ProjectImportRunRow>[]>(
    () => [
      {
        accessorKey: 'run_no',
        // Sized to fit and fixed: the grid truncates a resizable cell, and this one must
        // always read whole (browser pass N1 / N2).
        enableResizing: false,
        header: ({ column }) => <DataGridColumnHeader title="Run no." column={column} />,
        size: 120,
        meta: { headerTitle: 'Run no.', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <span className="font-medium">{row.original.run_no}</span>,
      },
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="File" column={column} />,
        size: 140,
        meta: { headerTitle: 'File', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.filename ?? ''}>
            {row.original.filename}
          </span>
        ),
      },
      {
        accessorKey: 'uploaded_by',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded by" column={column} />,
        size: 120,
        meta: { headerTitle: 'Uploaded by', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.uploaded_by ?? ''}>
            {row.original.uploaded_by ?? '-'}
          </span>
        ),
      },
      {
        accessorKey: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded on" column={column} />,
        size: 115,
        meta: { headerTitle: 'Uploaded on', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => formatDateSafe(row.original.uploaded_at),
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 130,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <RunStatusBadge status={row.original.status} />,
      },
      {
        accessorKey: 'rows',
        header: ({ column }) => <DataGridColumnHeader title="Rows" column={column} />,
        size: 70,
        meta: { headerTitle: 'Rows' },
        cell: ({ row }) => <Num value={row.original.rows} />,
      },
      {
        accessorKey: 'created',
        header: ({ column }) => <DataGridColumnHeader title="Created" column={column} />,
        size: 80,
        meta: { headerTitle: 'Created' },
        cell: ({ row }) => <Num value={row.original.created} />,
      },
      {
        accessorKey: 'skipped',
        header: ({ column }) => <DataGridColumnHeader title="Skipped" column={column} />,
        size: 80,
        meta: { headerTitle: 'Skipped' },
        cell: ({ row }) => <Num value={row.original.skipped} />,
      },
      {
        accessorKey: 'to_review',
        header: ({ column }) => <DataGridColumnHeader title="To review" column={column} />,
        size: 85,
        meta: { headerTitle: 'To review' },
        cell: ({ row }) => <Num value={row.original.to_review} />,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  const activeFilters = (status.length ? 1 : 0) + (uploadedBy.length ? 1 : 0);

  return (
    <>
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={runs.isLoading}
        error={runs.error}
        onRetry={() => void runs.refetch()}
        isPlaceholderData={runs.isPlaceholderData}
        onRowClick={(row: ProjectImportRunRow) => router.push(rowHref(row))}
        listingKey="projects.import.view"
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-semibold">
              {filtered ? 'No imports match' : 'No imports yet'}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {filtered ? 'Clear the filters to see every import.' : 'Uploaded workbooks show here.'}
            </p>
          </div>
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  isSettling={isSearchInFlight(isSettling, runs.isFetching, debouncedValue)}
                  placeholder="Search run no. or file"
                  aria-label="Search imports"
                  className="w-full sm:w-56 md:w-64"
                />
              }
              filters={{
                kind: 'custom',
                active: activeFilters > 0,
                activeCount: activeFilters,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Status</Label>
                      <SearchableMultiSelect
                        value={status}
                        onChange={setStatus}
                        options={STATUS_OPTIONS}
                        clearable
                        placeholder="All statuses"
                        aria-label="Status"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Uploaded by</Label>
                      <SearchableMultiSelect
                        value={uploadedBy}
                        onChange={setUploadedBy}
                        fetchOptions={async (query) =>
                          (await getUsersSelect({ query })).map((u) => ({
                            value: u.id,
                            label: u.name ?? '',
                          }))
                        }
                        clearable
                        placeholder="Anyone"
                        aria-label="Uploaded by"
                      />
                    </div>
                    {activeFilters > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setStatus([]);
                          setUploadedBy([]);
                        }}
                      >
                        Clear filters
                      </Button>
                    )}
                  </div>
                ),
              }}
              exportConfig={false}
              onRefresh={() => void runs.refetch()}
              isRefreshing={runs.isFetching && !runs.isLoading}
              primaryAction={
                canRun ? (
                  <Button onClick={() => setCreating(true)}>
                    <Plus className="size-4" aria-hidden />
                    Create
                  </Button>
                ) : undefined
              }
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
      {canRun && <CreateImportDialog open={creating} onOpenChange={setCreating} />}
    </>
  );
}

export default ProjectImportListClient;
