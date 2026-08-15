'use client';

/**
 * The captain's review queue (UAC AC-6.1).
 *
 * A request is a batch of people waiting on one decision, so the row answers
 * the two questions that decide whether he opens it: who asked, and how many
 * people are waiting.
 */

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type RowSelectionState,
  type SortingState,
} from '@tanstack/react-table';
import { ChevronRight, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { NewOnboardingRequestDialog } from './NewOnboardingRequestDialog';
import {
  ONBOARDING_STATUS_LABELS,
  ONBOARDING_STATUS_PILL_CODES,
  type OnboardingRequestStatus,
  type OnboardingRequestSummary,
} from '@/components/common/onboarding/types';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';
import { useOnboardingRequests } from '../hooks/useOnboardingRequests';

const STATUS_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  ...(Object.keys(ONBOARDING_STATUS_LABELS) as OnboardingRequestStatus[]).map((status) => ({
    value: status,
    label: ONBOARDING_STATUS_LABELS[status],
  })),
];

/** Stored naive UTC, read as Malaysia wall-clock, never as the browser's zone. */
function day(value: string | null): string {
  return value ? formatDateInMalaysia(value) : '-';
}

export function OnboardingRequestList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const listParams = {
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    statusKey: statusFilter === 'all' ? undefined : statusFilter,
  };

  const { data, isLoading, refetch, isFetching } = useOnboardingRequests(listParams);

  // A selection that survives a page or filter change points at rows that are
  // no longer on screen, which is what makes a bulk action act on the wrong set.
  useEffect(() => {
    setRowSelection({});
  }, [searchQuery, statusFilter, pagination.pageIndex, pagination.pageSize, sorting]);

  const columns = useMemo<ColumnDef<OnboardingRequestSummary>[]>(
    () => [
      buildSelectColumn<OnboardingRequestSummary>(),
      {
        id: 'title',
        accessorFn: (row) => row.title,
        header: ({ column }) => <DataGridColumnHeader title="Request" column={column} />,
        size: 220,
        meta: { headerTitle: 'Request', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="font-medium truncate block" title={row.original.title}>
            {row.original.title}
          </span>
        ),
      },
      {
        id: 'company_name',
        accessorFn: (row) => row.company_name,
        header: ({ column }) => <DataGridColumnHeader title="Company" column={column} />,
        size: 180,
        meta: { headerTitle: 'Company', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.company_name}>
            {row.original.company_name}
          </span>
        ),
      },
      {
        id: 'requester_name',
        accessorFn: (row) => row.requester_name,
        header: ({ column }) => <DataGridColumnHeader title="From" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'From', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate" title={row.original.requester_name}>
              {row.original.requester_name}
            </p>
            <p className="text-xs text-muted-foreground truncate" title={row.original.requester_email}>
              {row.original.requester_email}
            </p>
          </div>
        ),
      },
      {
        id: 'people_count',
        accessorFn: (row) => row.people_count,
        header: ({ column }) => <DataGridColumnHeader title="People" column={column} />,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'People', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => <span>{row.original.people_count}</span>,
      },
      {
        id: 'status',
        accessorFn: (row) => row.status,
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass(
              ONBOARDING_STATUS_PILL_CODES[row.original.status],
            )}`}
          >
            {ONBOARDING_STATUS_LABELS[row.original.status]}
          </span>
        ),
      },
      {
        id: 'submitted_at',
        accessorFn: (row) => row.submitted_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Submitted" column={column} />,
        size: 140,
        meta: { headerTitle: 'Submitted', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span className="truncate block" title={day(row.original.submitted_at)}>
            {day(row.original.submitted_at)}
          </span>
        ),
      },
      {
        id: 'expires_at',
        accessorFn: (row) => row.expires_at,
        header: ({ column }) => <DataGridColumnHeader title="Link expires" column={column} />,
        size: 140,
        meta: { headerTitle: 'Link expires', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span className="truncate block" title={day(row.original.expires_at)}>
            {day(row.original.expires_at)}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 40,
        enableHiding: false,
        enableSorting: false,
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
      },
    ],
    [],
  );

  const total = data?.pagination.total ?? 0;

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      emptyMessage="No onboarding requests yet. Create one to get started."
      onRowClick={(row) => {
        // Carry the active list query into the detail URL so its prev/next pager
        // walks the same filtered+sorted set.
        const search = buildDetailSearch(
          {
            pageIndex: pagination.pageIndex,
            pageSize: pagination.pageSize,
            sorting,
            searchQuery,
          },
          { status_key: statusFilter === 'all' ? undefined : statusFilter },
        );
        const id = (row as OnboardingRequestSummary).id;
        router.push(`/user-management/onboarding-requests/${id}${search ? `?${search}` : ''}`);
      }}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search requests..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery ? (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                ) : null}
              </div>
            }
            filters={{
              kind: 'custom',
              active: statusFilter !== 'all',
              activeCount: statusFilter !== 'all' ? 1 : 0,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={(value) => {
                        setStatusFilter(value || 'all');
                        setPagination((p) => ({ ...p, pageIndex: 0 }));
                      }}
                      options={STATUS_OPTIONS}
                      placeholder="All statuses"
                      triggerClassName="mt-1"
                    />
                  </div>
                  {statusFilter !== 'all' ? (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setStatusFilter('all');
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                      >
                        Clear filters
                      </Button>
                    </div>
                  ) : null}
                </div>
              ),
            }}
            exportConfig={{ filename: 'onboarding_requests_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={<NewOnboardingRequestDialog />}
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
