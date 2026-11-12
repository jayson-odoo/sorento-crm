'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { DatePicker } from '@/components/ui/date-picker';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useServiceJobsList, useTechniciansSelect } from '../hooks/useServiceJobs';
import { useServiceJobMoves } from '../hooks/useServiceJobMoves';
import { nextStepFor, secondaryMoves } from '../lib/nextStep';
import { ymd } from '../lib/jobDates';
import { listUrlSearch } from '../lib/listUrl';
import type { ServiceJob, ServiceJobStatus } from '../types/serviceJob.types';
import ServiceJobStatusPill from './ServiceJobStatusPill';

const STATUS_OPTIONS: { value: ServiceJobStatus; label: string }[] = [
  { value: 'proposed', label: 'Proposed' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'on_the_way', label: 'On the way' },
  { value: 'arrived', label: 'Arrived' },
  { value: 'completed', label: 'Completed' },
  { value: 'verified', label: 'Verified' },
  { value: 'cancelled', label: 'Cancelled' },
];

function parseYmd(value: string): Date | undefined {
  const [y, m, d] = value.split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d) : undefined;
}

function Text({ value }: { value: string | null | undefined }) {
  return (
    <span className="block truncate" title={value ?? undefined}>
      {value || '-'}
    </span>
  );
}

export default function ServiceJobsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'scheduled_from', desc: true }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearchQuery,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [technicianFilter, setTechnicianFilter] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [menuJob, setMenuJob] = useState<ServiceJob | null>(null);

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearchQuery(state.searchQuery);
    setStatusFilter(splitMulti(state.filters.status));
    setTechnicianFilter(splitMulti(state.filters.technician_id));
    setDateFrom(state.filters.date_from ?? '');
    setDateTo(state.filters.date_to ?? '');
  });
  useResetPageOnFilterChange(setPagination, [
    searchQuery,
    statusFilter.join(','),
    technicianFilter.join(','),
    dateFrom,
    dateTo,
  ]);

  // The list keeps ALL its state in its own address, so the browser's Back restores it.
  const filtersKey = [statusFilter.join(','), technicianFilter.join(','), dateFrom, dateTo].join('|');
  useEffect(() => {
    const next = listUrlSearch(window.location.search, {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      filters: {
        status: statusFilter.length ? joinMulti(statusFilter) : undefined,
        technician_id: technicianFilter.length ? joinMulti(technicianFilter) : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      },
    });
    if (next !== window.location.search.replace(/^\?/, '')) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}?${next}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.pageIndex, pagination.pageSize, sorting, searchQuery, filtersKey]);

  const { data, isLoading, isPlaceholderData, isFetching, refetch, error } = useServiceJobsList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter,
    technician_id: technicianFilter,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });
  const { data: technicians = [] } = useTechniciansSelect();
  const moves = useServiceJobMoves();

  const filtersActiveCount =
    (statusFilter.length ? 1 : 0) +
    (technicianFilter.length ? 1 : 0) +
    (dateFrom || dateTo ? 1 : 0);

  const rowHref = (row: ServiceJob) => {
    const search = buildDetailSearch(
      { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
      {
        status: statusFilter.length ? joinMulti(statusFilter) : undefined,
        technician_id: technicianFilter.length ? joinMulti(technicianFilter) : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      },
    );
    return `/complaint-management/service-jobs/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<ServiceJob>[]>(
    () => [
      {
        id: 'job_number',
        accessorFn: (r) => r.job_number,
        header: ({ column }) => <DataGridColumnHeader title="Job no." column={column} />,
        size: 140,
        cell: ({ row }) => <Text value={row.original.job_number} />,
        meta: { headerTitle: 'Job no.', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'complaint_number',
        accessorFn: (r) => r.complaint_number,
        header: ({ column }) => <DataGridColumnHeader title="Complaint no." column={column} />,
        size: 165,
        cell: ({ row }) => <Text value={row.original.complaint_number} />,
        meta: { headerTitle: 'Complaint no.', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'status',
        accessorFn: (r) => r.status,
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 110,
        cell: ({ row }) => (
          <ServiceJobStatusPill status={row.original.status} label={row.original.status_label} />
        ),
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'scheduled_from',
        accessorFn: (r) => r.scheduled_from,
        header: ({ column }) => <DataGridColumnHeader title="Scheduled" column={column} />,
        size: 160,
        cell: ({ row }) => (
          <Text
            value={
              row.original.scheduled_from
                ? formatDateTimeInMalaysia(row.original.scheduled_from)
                : null
            }
          />
        ),
        meta: { headerTitle: 'Scheduled', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'technician',
        accessorFn: (r) => r.technician_name,
        header: ({ column }) => <DataGridColumnHeader title="Technician" column={column} />,
        size: 110,
        cell: ({ row }) => <Text value={row.original.technician_name} />,
        meta: { headerTitle: 'Technician', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'city',
        accessorFn: (r) => r.city,
        header: ({ column }) => <DataGridColumnHeader title="City" column={column} />,
        size: 90,
        cell: ({ row }) => <Text value={row.original.city} />,
        meta: { headerTitle: 'City', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'customer',
        accessorFn: (r) => r.customer_name,
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        size: 100,
        cell: ({ row }) => <Text value={row.original.customer_name} />,
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-32" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  const menuStep = menuJob ? nextStepFor(menuJob) : null;

  return (
    <>
      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            // Capture phase: a right-click outside a row stops here, so the browser's own menu
            // shows instead of an empty one.
            onContextMenuCapture={(event) => {
              const rowEl = (event.target as Element).closest('[data-job-id]');
              const job = (data?.data ?? []).find((j) => j.id === rowEl?.getAttribute('data-job-id'));
              if (!job) {
                event.stopPropagation();
                return;
              }
              setMenuJob(job);
            }}
          >
            <DataGrid
              table={table}
              recordCount={data?.pagination.total || 0}
              isLoading={isLoading}
              isPlaceholderData={isPlaceholderData}
              error={error}
              onRetry={() => void refetch()}
              rowHref={rowHref}
              rowAttributes={(row) => ({ 'data-job-id': row.id })}
              emptyMessage="No service jobs"
              standardToolbar={false}
              tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
            >
              <Card>
                <CardHeader className="block">
                  <DataGridListToolbar
                    table={table}
                    searchSlot={
                      <ListSearchInput
                        value={searchInput}
                        onChange={setSearchInput}
                        isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                        placeholder="Search service jobs..."
                        className="w-64"
                      />
                    }
                    filters={{
                      kind: 'custom',
                      active: filtersActiveCount > 0,
                      activeCount: filtersActiveCount,
                      content: (
                        <div className="space-y-4">
                          <div>
                            <Label>Status</Label>
                            <SearchableMultiSelect
                              value={statusFilter}
                              onChange={setStatusFilter}
                              options={STATUS_OPTIONS}
                              placeholder="All statuses"
                              triggerClassName="mt-1"
                              clearable
                            />
                          </div>
                          <div>
                            <Label>Technician</Label>
                            <SearchableMultiSelect
                              value={technicianFilter}
                              onChange={setTechnicianFilter}
                              options={technicians.map((t) => ({ value: t.id, label: t.name }))}
                              placeholder="All technicians"
                              triggerClassName="mt-1"
                              clearable
                            />
                          </div>
                          <div className="grid grid-cols-1 gap-2">
                            <div>
                              <Label>Scheduled from</Label>
                              <DatePicker
                                value={dateFrom ? parseYmd(dateFrom) : undefined}
                                onChange={(d) => setDateFrom(d ? ymd(d) : '')}
                                ariaLabel="Scheduled from"
                                portal
                              />
                            </div>
                            <div>
                              <Label>Scheduled to</Label>
                              <DatePicker
                                value={dateTo ? parseYmd(dateTo) : undefined}
                                onChange={(d) => setDateTo(d ? ymd(d) : '')}
                                ariaLabel="Scheduled to"
                                portal
                              />
                            </div>
                          </div>
                        </div>
                      ),
                    }}
                    onRefresh={() => void refetch()}
                    isRefreshing={isFetching && !isLoading}
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
        <ContextMenuContent className="w-60">
          {menuJob && (
            <>
              <ContextMenuItem
                onSelect={() => router.push(`/complaint-management/complaints/${menuJob.complaint_id}`)}
              >
                Open complaint
              </ContextMenuItem>
              {(menuStep || secondaryMoves(menuJob.status, !!menuJob.technician_id).length > 0) && <ContextMenuSeparator />}
              {menuStep && (
                <ContextMenuItem onSelect={() => moves.runStep(menuJob, menuStep)}>
                  {menuStep.label}
                </ContextMenuItem>
              )}
              {menuJob.technician_id && (menuJob.status === 'proposed' || menuJob.status === 'confirmed') && (
                <ContextMenuItem onSelect={() => moves.changeTechnician(menuJob)}>Change technician</ContextMenuItem>
              )}
              {secondaryMoves(menuJob.status, !!menuJob.technician_id).map((m) => (
                <ContextMenuItem key={`${m.to}-${m.label}`} onSelect={() => moves.runMove(menuJob, m)}>
                  {m.label}
                </ContextMenuItem>
              ))}
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>
      {moves.dialogs}
    </>
  );
}
