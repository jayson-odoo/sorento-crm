'use client';

/**
 * Every service job, findable without knowing which day it is on.
 *
 * The dispatch board answers "who is working today". That is the right question at 8am and
 * the wrong one every other time: it filters on a single day's `scheduled_from`, so a job
 * proposed with no date yet - the state every job starts in - is on no day at all, and a
 * job confirmed for last Tuesday leaves the board the moment it moves on. Raise a job,
 * look for it tomorrow, and it has vanished. This list is where it lives.
 *
 * Built on the shared `DataGrid` rather than a hand-rolled table, like every other listing
 * in the product: column visibility, resizing, pagination, export and the toolbar are
 * behaviours the grid already has and a bespoke `<table>` would have to re-learn one bug
 * at a time (ARCHITECTURE-RULES).
 *
 * No "Add" button, deliberately. A job is raised FROM a case - the complaint's own Service
 * Jobs section - because it copies that case's reported site. An Add button here would
 * open a form with no site to copy.
 */

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { CalendarRange, ChevronRight, Search, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  SERVICE_JOB_STATUS_LABELS,
  formatDuration,
  listServiceJobs,
  type ServiceJob,
  type ServiceJobStatusKey,
} from '../services/serviceJobService';

const ALL = '__all__';

export default function ServiceJobsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>(ALL);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['service-jobs-list', pagination, sorting, searchQuery, statusFilter],
    queryFn: () =>
      listServiceJobs({
        page: pagination.pageIndex + 1,
        limit: pagination.pageSize,
        query: searchQuery.trim() || undefined,
        status: statusFilter === ALL ? undefined : [statusFilter],
        sort: sorting[0]?.id,
        dir: sorting[0]?.desc ? 'desc' : 'asc',
      }),
  });

  const columns = useMemo<ColumnDef<ServiceJob>[]>(
    () => [
      {
        accessorKey: 'job_number',
        header: ({ column }) => <DataGridColumnHeader title="Job" column={column} />,
        cell: ({ row }) => (
          <span className="font-medium">{row.original.job_number ?? 'Unnumbered'}</span>
        ),
        size: 160,
        meta: { headerTitle: 'Job', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'site_address',
        header: ({ column }) => <DataGridColumnHeader title="Site" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.site_address ?? ''}>
            {row.original.site_address || '-'}
          </span>
        ),
        size: 320,
        enableSorting: false,
        meta: { headerTitle: 'Site', skeleton: <Skeleton className="h-4 w-48" /> },
      },
      {
        accessorKey: 'scheduled_from',
        header: ({ column }) => <DataGridColumnHeader title="Scheduled" column={column} />,
        cell: ({ row }) =>
          row.original.scheduled_from ? (
            formatDateTimeInMalaysia(row.original.scheduled_from)
          ) : (
            // The commonest state, and not a gap in the data: nobody has agreed a time
            // yet, which is exactly what Proposed means. A blank cell reads as missing.
            <span className="text-muted-foreground">Not scheduled</span>
          ),
        size: 180,
        meta: { headerTitle: 'Scheduled', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'attend_seconds',
        header: ({ column }) => <DataGridColumnHeader title="Attended In" column={column} />,
        cell: ({ row }) =>
          row.original.attend_seconds !== null
            ? formatDuration(row.original.attend_seconds)
            : '-',
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Attended In', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'status_key',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status_key)}`}
          >
            {row.original.status_key
              ? SERVICE_JOB_STATUS_LABELS[row.original.status_key as ServiceJobStatusKey]
              : 'Unknown'}
          </span>
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-5 w-20" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
        enableHiding: false,
        enableSorting: false,
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
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const filtersActiveCount = statusFilter === ALL ? 0 : 1;

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={(row: ServiceJob) =>
        router.push(`/complaint-management/service-jobs/${row.id}`)
      }
      standardToolbar={false}
      tableLayout={{ columnsVisibility: true, columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search service jobs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: filtersActiveCount > 0,
              activeCount: filtersActiveCount,
              content: (
                <div className="space-y-3">
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={setStatusFilter}
                      options={[
                        { value: ALL, label: 'All statuses' },
                        ...Object.entries(SERVICE_JOB_STATUS_LABELS).map(
                          ([value, label]) => ({ value, label }),
                        ),
                      ]}
                      placeholder="All statuses"
                      triggerClassName="mt-1"
                    />
                  </div>
                  {filtersActiveCount > 0 && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setStatusFilter(ALL)}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'service_jobs_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              // The board, not an Add: a job is raised from the case whose site it copies.
              <Button
                variant="outline"
                onClick={() => router.push('/complaint-management/service-jobs/board')}
              >
                <CalendarRange />
                Dispatch board
              </Button>
            }
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
